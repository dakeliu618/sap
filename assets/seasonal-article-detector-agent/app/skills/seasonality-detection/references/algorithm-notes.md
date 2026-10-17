# Algorithm Reference Notes

## STL Decomposition (Seasonal and Trend decomposition using Loess)

STL splits a time-series Y(t) into three additive components:
- **Trend** T(t): the long-run direction (growth, decline, flat)
- **Seasonal** S(t): the repeating pattern at a fixed frequency (52 weeks for annual seasonality)
- **Residual** R(t): the noise not explained by trend or seasonal

Formula: `Y(t) = T(t) + S(t) + R(t)`

## Seasonal Strength Index

Measures what fraction of variance is explained by the seasonal component vs. noise:

`strength = 1 - Var(R) / Var(S + R)`

- Range: 0 to 1 (can be negative if Var(R) > Var(S+R), clamped to 0)
- > 0.4: candidate for seasonal classification
- > 0.6: strong seasonal signal
- > 0.8: very strong, clear seasonal pattern

## Cross-Year Consistency

Pearson correlation coefficient between the seasonal patterns of consecutive years (aligned to 52-week windows). High consistency (>0.7) means the seasonal pattern repeats reliably year over year — a key indicator that it is driven by a real seasonal phenomenon rather than a one-off event.

## Practical Notes

- Weekly granularity is preferred (period=52). Daily data can be used but increases computation time significantly.
- For articles with strong promotions, the seasonal component may include promotional lift — this is expected and reflects real demand behavior.
- Articles with fewer than 2 years of data should be flagged as INSUFFICIENT_DATA and excluded from automatic replenishment triggering.
