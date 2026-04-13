import logging
from datetime import date

from django.core.cache import cache

from .analyzer import SpendingAnalyzer
from .llm import LLMConnector

logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 60 * 60 * 24  # 24 hours


def run_insight_engine(user, reference_date: date = None) -> dict:
    """
    Main entry point for the Insight Engine.

    Execution order:
      1. Compute the subject month from reference_date (defaults to today).
      2. Check the cache — if a valid result exists, return it immediately.
      3. Run SpendingAnalyzer to produce the summary packet (2 DB queries).
      4. Run LLMConnector to generate the narrative string.
      5. Store the combined result in cache for 24 hours.
      6. Return the full response dict.

    Returns:
        {
            "narrative":    str,
            "analysis":     dict  (summary packet from SpendingAnalyzer),
            "cached":       bool,
            "used_fallback": bool,
        }
    """
    today = reference_date or date.today()

    # Derive the subject month label for the cache key
    from dateutil.relativedelta import relativedelta
    subject_month = (date(today.year, today.month, 1) - relativedelta(months=1)).strftime('%Y-%m')

    cache_key = f"insight_{user.id}_{subject_month}"

    # --- Cache hit ---
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        logger.info(
            f"run_insight_engine: cache hit — user='{user.username}' (id={user.id}) "
            f"| key={cache_key}"
        )
        cached_result['cached'] = True
        return cached_result

    logger.info(
        f"run_insight_engine: cache miss — user='{user.username}' (id={user.id}) "
        f"| key={cache_key} | running full analysis"
    )

    # --- Analysis ---
    analyzer = SpendingAnalyzer(user, reference_date=today)
    packet   = analyzer.run()

    # --- LLM synthesis ---
    connector = LLMConnector()
    narrative, used_fallback = connector.generate(packet)

    result = {
        'narrative':     narrative,
        'analysis':      packet,
        'cached':        False,
        'used_fallback': used_fallback,
    }

    # --- Cache store ---
    # Only cache if there is real data — no point caching an empty packet
    # for 24 hours as the user may add transactions soon after.
    if packet['categories']:
        cache.set(cache_key, result, CACHE_TIMEOUT)
        logger.info(
            f"run_insight_engine: result cached — key={cache_key} | "
            f"timeout={CACHE_TIMEOUT}s"
        )
    else:
        logger.info(
            f"run_insight_engine: empty packet, skipping cache — key={cache_key}"
        )

    return result
