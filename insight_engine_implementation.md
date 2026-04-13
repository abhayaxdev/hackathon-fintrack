# Insight Engine Implementation Notes

This document records every design decision, tradeoff, and implementation detail
for the monthly Insight Engine added to the FinTrack backend.

---

## Overview

The Insight Engine is a read-only feature that runs on demand for an authenticated
user. It:

1. Pulls two months of spending data from the database (`SpendingAnalyzer`)
2. Computes per-category and overall variance
3. Feeds a structured summary to Gemini to generate a short conversational narrative (`LLMConnector`)
4. Caches the full result for 24 hours to avoid redundant DB queries and LLM API calls (`pipeline`)
5. Exposes everything through a single `GET /api/insights/` endpoint (`InsightView`)

No new models or migrations are required — the engine is purely analytical and
reads exclusively from the existing `Transaction` table.

---

## File Structure

```
core/
└── insights/
    ├── __init__.py
    ├── analyzer.py     # SpendingAnalyzer
    ├── llm.py          # LLMConnector
    └── pipeline.py     # run_insight_engine()
```

`InsightView` lives in `core/views.py` alongside all other views.
The route `GET /api/insights/` is registered in `core/urls.py`.

---

## `SpendingAnalyzer` (`analyzer.py`)

### What it does

Compares a user's expense transactions between two consecutive complete calendar
months:

- **Subject month** — the last complete month (e.g. if today is April 13, subject = March)
- **Baseline month** — the month before the subject (e.g. February)

### Why two complete months instead of current-month-to-date

Using the current month as the subject would mean comparing 13 days of April
spending against a full 31-day March, making every category look cheaper than
it actually is. Using two complete, closed months gives an honest apples-to-apples
comparison with no pro-rating correction needed.

### The queries

Exactly **two SQL queries** are issued per engine run:

```python
# Q1 — subject month
Transaction.objects.filter(
    user=user,
    transaction_type='expense',
    date__gte=subject_start,
    date__lte=subject_end,
).values('category__name').annotate(total=Sum('amount'))

# Q2 — baseline month (same shape, different date window)
```

Both queries use `.values('category__name').annotate(total=Sum('amount'))` —
Django translates this to a single `SELECT category__name, SUM(amount) GROUP BY
category__name` query. No `Transaction` instances are ever loaded into Python
memory; only the aggregated rows are returned.

### Variance calculation

```python
variance_pct = ((current - baseline) / baseline) * 100
```

Computed in Python on two small dicts (one per query). The three edge cases are
handled explicitly:

| Situation | Handling |
|---|---|
| Category in subject but not baseline | `variance_pct = None`, labelled "new category" in prompt |
| Category in baseline but not subject | `this_month = 0`, `variance_pct = -100%` |
| No data at all in either month | Returns `_empty_packet()` with empty `categories` list |

### Why `Uncategorised` as fallback

`Transaction.category` is nullable (`SET_NULL`). If a category is deleted, the FK
becomes `NULL`. Rather than silently dropping those transactions from the analysis,
they are grouped under `'Uncategorised'` so their spend is still represented in
the totals.

### Output — the Summary Packet

```json
{
    "subject_month":      "2026-03",
    "baseline_month":     "2026-02",
    "total_this_month":   18400.00,
    "total_last_month":   15200.00,
    "total_variance_pct": 21.05,
    "categories": [
        {
            "category":     "Food",
            "this_month":   5200.00,
            "last_month":   3700.00,
            "variance_pct": 40.54
        },
        ...
    ]
}
```

This packet serves two purposes:
1. Sent to the LLM for narrative generation
2. Returned directly in the API response for Flutter chart rendering

---

## `LLMConnector` (`llm.py`)

### Provider: Gemini

**Why Gemini over OpenAI:** Gemini's free tier (via Google AI Studio) requires no
credit card and has generous daily limits — appropriate for a hackathon where
billing surprises are a risk. The `google-generativeai` SDK (`0.8.3`) is a single
pip install. Switching to OpenAI later would only require changing `_call_gemini`
and the env var names.

### Prompt design

The summary packet is **not** sent as raw JSON. It is rendered into a readable
prose format by `_build_prompt()`:

```
Monthly spending comparison for a user based in Nepal.

Reference month: 2026-03
Previous month:  2026-02

Overall: spent 18,400.00 this month vs 15,200.00 last month (+21.1% change).

Breakdown by category:
  - Food: 5,200.00 this month vs 3,700.00 last month (+40.5%)
  - Transport: 800.00 this month vs 1,400.00 last month (-42.9%)
  ...
```

**Why prose over JSON in the prompt:** LLMs produce more natural, less
"data-dump" narratives when the context is framed as text rather than structured
data. Sending raw JSON often causes the model to simply restate the key-value
pairs rather than interpret them.

### System instruction

```
You are a supportive, professional financial coach for a user based in Nepal.
Do NOT list or repeat the raw numbers back to the user.
Instead, interpret what the numbers mean in plain, conversational language.
Provide exactly 2 to 3 short, actionable suggestions for the upcoming month.
Be encouraging but honest. Keep the entire response under 120 words.
```

**Why "Nepal" context in the persona:** The app's default currency is NRS and the
user base is Nepali. The persona grounds the LLM's suggestions in a local context
(e.g. it won't reference "your 401k" or suggest services unavailable in Nepal).

**Why the 120-word cap:** Mobile screens are small. A 400-word essay is
overwhelming and won't be read. Short, punchy suggestions are more actionable.

### Fallback narrative

```python
FALLBACK_NARRATIVE = (
    "Great job tracking your expenses! ..."
)
```

The fallback is returned in three situations:
1. `GEMINI_API_KEY` is not set in the environment
2. The summary packet has no categories (no transaction data)
3. The Gemini API call raises any exception (network error, rate limit, invalid key, etc.)

**Why a hardcoded fallback over raising an exception:** The Insight Engine is a
value-add feature — the app still works without it. An exception propagating up
to the Flutter app would break the insights screen entirely. The fallback ensures
the screen always renders something useful.

**Why log `WARNING` on API failure but not on missing key:** A missing key is a
configuration choice (developer running locally without a key). An API failure
during production is unexpected and warrants attention in the log file.

### `generate()` return signature

```python
def generate(packet: dict) -> tuple[str, bool]:
    # Returns (narrative_string, used_fallback)
```

`used_fallback` is surfaced in the API response so:
- The Flutter app can optionally show a different UI treatment for fallback text
- Developers can identify misconfigured deployments from API logs

---

## `run_insight_engine()` (`pipeline.py`)

### Execution order

```
1. Compute subject_month label  →  derive cache key
2. Cache hit?  →  return immediately (mark cached=True)
3. SpendingAnalyzer.run()       →  2 DB queries
4. LLMConnector.generate()      →  1 Gemini API call (or fallback)
5. Cache set (24 hours)         →  only if categories list is non-empty
6. Return result dict
```

### Cache key design

```python
cache_key = f"insight_{user.id}_{subject_month}"
# e.g. "insight_7_2026-03"
```

**Why include `subject_month`:** The cache must be invalidated automatically when
a new month begins. Using `user.id` alone would serve March's insight to a request
made in April. Including the month label means the April key is always a miss
until the first April request populates it.

**Why not invalidate on new transaction:** Invalidating every time the user adds a
transaction would defeat the purpose of caching — users on the insights screen
might be actively logging expenses. The 24-hour TTL is a deliberate tradeoff:
the insight is a monthly summary, not a live dashboard. Stale-by-hours is
acceptable.

### Why skip caching empty packets

```python
if packet['categories']:
    cache.set(cache_key, result, CACHE_TIMEOUT)
```

A new user who has never logged a transaction would get an empty packet cached for
24 hours. If they then log their first transaction, they'd be stuck seeing "no
data" until the cache expires. Skipping the cache for empty packets means the
engine retries on every request until there is actual data to show.

---

## Cache Backend

**Choice: `LocMemCache` (Django default)**

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'fintrack-cache',
    }
}
```

**Why `LocMemCache` for now:** This is a hackathon MVP running on a single
process. `LocMemCache` requires zero infrastructure — no Redis server, no extra
package. The cache is in-process memory and lives as long as the Django process.

**Tradeoff:** If you run multiple Gunicorn workers, each worker has its own
separate in-memory cache. Two users hitting different workers for the same month
would each trigger a full DB query + LLM call. For a single-worker dev/demo
server this is irrelevant.

**Upgrade path (documented in `settings.py` comment):**
```python
# pip install django-redis
# CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache", "LOCATION": "redis://127.0.0.1:6379/1"}}
```

---

## `InsightView` (`core/views.py`)

```python
class InsightView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        result = run_insight_engine(request.user)
        return Response(result, status=HTTP_200_OK)
```

**Why `APIView` instead of a `ViewSet`:** There is no collection to list, no
`pk` to retrieve, no create/update/delete. `APIView` with a single `get` method
is the minimal, correct abstraction. A `ViewSet` would add unnecessary router
overhead for a single endpoint.

**Why always `200 OK`:** Even when the LLM fallback is used or the packet is
empty, the response is still a valid, useful payload. `used_fallback=true` and
an empty `categories` list are application-level signals, not HTTP error
conditions.

---

## API Response Shape

`GET /api/insights/`

```json
{
    "narrative": "Your grocery spending climbed notably last month...",
    "analysis": {
        "subject_month": "2026-03",
        "baseline_month": "2026-02",
        "total_this_month": 18400.00,
        "total_last_month": 15200.00,
        "total_variance_pct": 21.05,
        "categories": [
            {
                "category": "Food",
                "this_month": 5200.00,
                "last_month": 3700.00,
                "variance_pct": 40.54
            }
        ]
    },
    "cached": false,
    "used_fallback": false
}
```

**Why include `analysis` alongside `narrative`:** The Flutter app needs both:
- `narrative` → rendered as a card with conversational text
- `analysis.categories` → rendered as a bar/pie chart comparing months

Returning both in one call avoids a second round-trip. The Flutter app does not
need to run the analysis separately.

---

## Environment Variables

Add to your `.env` file:

```env
# Get your free key at https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-1.5-flash   # optional, this is the default
```

If `GEMINI_API_KEY` is left blank, the engine runs in degraded mode: analysis
still works and returns the summary packet, but `narrative` will always be the
hardcoded fallback tip and `used_fallback` will be `true`.

---

## New Dependency

`google-generativeai==0.8.3` added to `requirements.txt`.

```bash
pip install -r requirements.txt
```

The import is **lazy** — it only happens inside `_call_gemini()`, which is only
called when a valid API key is present. The server starts and runs normally even
if the package is not installed, as long as `GEMINI_API_KEY` is not set (the
fallback path is taken before the import is reached).

---

## Logging Summary

| Event | Level | Location |
|---|---|---|
| Analyzer run started | `INFO` | `SpendingAnalyzer.run` |
| Analyzer complete | `INFO` | `SpendingAnalyzer.run` |
| No data found | `WARNING` | `SpendingAnalyzer.run` |
| Cache hit | `INFO` | `pipeline.run_insight_engine` |
| Cache miss, running analysis | `INFO` | `pipeline.run_insight_engine` |
| Result cached | `INFO` | `pipeline.run_insight_engine` |
| Empty packet, skipping cache | `INFO` | `pipeline.run_insight_engine` |
| API key not configured | `WARNING` | `LLMConnector.generate` |
| Gemini API call failed | `WARNING` | `LLMConnector.generate` |
| Gemini response received | `INFO` | `LLMConnector.generate` |
| InsightView response served | `INFO` | `InsightView.get` |
