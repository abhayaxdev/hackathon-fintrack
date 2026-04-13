# Flutter Insights Screen — UI Prompt

## Context

This prompt is for generating the Insights screen of the **FinTrack** Flutter app — a personal finance tracker for users in Nepal. The app is already fully set up with an existing theme (color scheme, text styles, card/component patterns). **Use the existing theme throughout. Do not hardcode colors or define new `ThemeData`.**

---

## Task

Build an `InsightsScreen` widget with static/mock data that reflects the shape of the real API response from `GET /api/insights/`. The screen must be structured for easy swap-out of the static mock with a live API call later.

---

## Static Mock Data

Place this as a `static const` or `final` at the top of the file:

```dart
final mockInsightResponse = {
  "narrative":
      "Your grocery spending climbed notably last month. Transport costs dropped significantly — great discipline there! Consider setting a Food budget cap for the coming month, reviewing your subscriptions, and keeping your transport habit going strong.",
  "analysis": {
    "subject_month": "2026-03",
    "baseline_month": "2026-02",
    "total_this_month": 18400.00,
    "total_last_month": 15200.00,
    "total_variance_pct": 21.05,
    "categories": [
      {"category": "Food",         "this_month": 5200.00, "last_month": 3700.00, "variance_pct": 40.54},
      {"category": "Transport",    "this_month":  800.00, "last_month": 1400.00, "variance_pct": -42.86},
      {"category": "Shopping",     "this_month": 4100.00, "last_month": 3800.00, "variance_pct": 7.89},
      {"category": "Utilities",    "this_month": 2200.00, "last_month": 2200.00, "variance_pct": 0.0},
      {"category": "Uncategorised","this_month": 6100.00, "last_month": 4100.00, "variance_pct": 48.78},
    ],
  },
  "cached": false,
  "used_fallback": false,
};
```

---

## Screen Layout (top to bottom)

### 1. Header
- Title: **"Monthly Insights"**
- Subtitle: month range derived from `subject_month` / `baseline_month` fields (format `yyyy-MM`), rendered as e.g. **"March vs February 2026"**

### 2. Narrative Card
- A themed `Card` displaying the `narrative` string as conversational body text.
- If `used_fallback` is `true`, show a small muted label **"General tip"** above the text to distinguish it from personalized AI analysis.

### 3. Overall Summary Row
- Two stat tiles side by side: **"This Month"** and **"Last Month"** showing `total_this_month` and `total_last_month`.
- The `total_variance_pct` displayed prominently between or below the tiles.
  - **Green** if negative (spent less than last month).
  - **Red** if positive (spent more than last month).
  - Use `colorScheme.error` for red and a success-appropriate color from the existing theme for green.

### 4. Category Bar Chart
- A grouped horizontal bar chart comparing `this_month` vs `last_month` per category.
- Use **two visually distinct colors from the existing theme** for the two bar series.
- If `fl_chart` is already in `pubspec.yaml`, use it. Otherwise, implement a simple custom-painted bar chart — **do not add new dependencies**.
- Each bar group should display the category name as a label.
- Show the `variance_pct` as a small colored badge or directional arrow next to each group (green ↓ for decrease, red ↑ for increase, neutral for zero).

### 5. Category List
- A scrollable list below the chart.
- Each row: category name | this-month amount | last-month amount | variance badge.
- Variance badge: colored pill/chip — green for negative, red for positive, neutral for zero.

---

## Formatting Rules

- All currency amounts formatted as `NRS X,XXX.XX`.
- Month labels parsed from `yyyy-MM` strings using `DateFormat` (`intl` package, already available) and rendered as `"March 2026"`.
- The `cached` field is informational only — ignore it in the UI.

---

## Behavior

- Wrap the entire screen in a `RefreshIndicator` as a placeholder for future live API integration.
- The screen should be a `StatefulWidget` to support the `RefreshIndicator` callback.
- All data flows from the single mock constant — no logic should be hardcoded inline.

---

## Empty State

If `analysis.categories` is empty, show a centered illustration/icon and message:
**"No spending data yet. Start logging transactions to see your insights."**
