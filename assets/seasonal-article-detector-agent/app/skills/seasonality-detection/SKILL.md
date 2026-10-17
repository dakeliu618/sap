---
name: seasonality-detection
description: Step-by-step instructions for running seasonal strength analysis on article/store time-series data including algorithm selection, threshold evaluation, and confidence scoring
---

# Seasonality Detection Skill

## When to Use This Skill

Load this skill when the user requests classification, detection, or re-analysis of seasonal articles, or when you need to interpret or explain seasonality results.

## Algorithm Steps

1. **Retrieve time-series data** using the `read_carab_timeseries` tool for the requested scope and date range.
2. **Run STL decomposition** via the `run_seasonality_detection` tool. This decomposes each article/store time-series into trend, seasonal, and residual components.
3. **Seasonal strength index** = `1 - Var(residual) / Var(seasonal + residual)`. Range: 0 (no seasonality) to 1 (perfect seasonality).
4. **Season window identification**: calendar weeks where the seasonal component exceeds 1 standard deviation above its mean.
5. **Confidence scoring**: composite of (a) data length score — 3 full years = 100%; (b) signal-to-noise ratio of seasonal vs. residual; (c) cross-year consistency — correlation of seasonal pattern across consecutive years.

## Threshold Rules

| Parameter | Default | Environment Variable |
|-----------|---------|---------------------|
| Seasonal strength threshold | 0.4 | `SEASONAL_STRENGTH_THRESHOLD` |
| Minimum confidence | 60% | `MIN_CONFIDENCE_THRESHOLD` |
| Minimum data history | 2 years | `MIN_DATA_YEARS` |

These can be adjusted per category or product group by the user.

## Classification Decision Table

| Condition | Label |
|-----------|-------|
| strength ≥ threshold AND confidence ≥ 60% | `SEASONAL` |
| strength ≥ threshold AND confidence < 60% | `LOW_CONFIDENCE_SEASONAL` |
| strength < threshold | `NON_SEASONAL` |
| fewer than MIN_DATA_YEARS of weekly data | `INSUFFICIENT_DATA` |

## Output Format

For each article/store combination:
- `article_id` — article identifier
- `store_id` — store identifier
- `classification` — one of the labels above
- `confidence_score` — 0–100%
- `season_start_week` — calendar week when season begins (or null)
- `season_end_week` — calendar week when season ends (or null)
- `seasonal_strength_index` — 0–1
- `algorithm_used` — `stl`
- `data_range_start`, `data_range_end` — dates of the input data

## Important Guardrails

- Never forward `LOW_CONFIDENCE_SEASONAL` articles to the replenishment workflow without explicit user confirmation.
- Report `INSUFFICIENT_DATA` articles clearly — do not produce a classification for them.
- If the user asks to adjust thresholds, acknowledge the change and re-run detection with the updated config dict.
