# Dashboard metric definitions

Use the canonical fields below when refreshing or rebuilding the Power BI report.

| Display metric | Source field | Definition |
|---|---|---|
| Daily long-short return (EW) | `fct_signal_daily.long_short_return_ew` | Equal-weighted Q5 return minus equal-weighted Q1 return for `close(date_t) -> close(next trading day)` |
| Cumulative return (EW) | `fct_signal_daily.cumulative_return_ew` | Compounded daily EW long-short returns from the start of the modeled sample |
| Daily long-short return (LW) | `fct_signal_daily.long_short_return_lw` | Dollar-volume-weighted Q5 return minus Q1 return |
| Cumulative return (LW) | `fct_signal_daily.cumulative_return_lw` | Compounded daily LW long-short returns from the start of the modeled sample |
| Cumulative spread | `fct_signal_daily.cumulative_spread_ew` | Arithmetic sum for diagnostics only; do not label it portfolio return |

The current model defines each long-short portfolio as one unit long plus one unit short: 200% gross exposure, 0% net exposure, before financing, borrow fees, transaction costs, and slippage.

Legacy fields `spread_ew`, `spread_vw`, `q5_return_vw`, and `q1_return_vw` remain available so the existing report can refresh. New visuals and measures should use the explicit `long_short_*` and `*_lw` names above.

For a date slicer that should rebase cumulative performance at the selected start date, define a measure using the selected daily returns rather than summing them:

```DAX
Cumulative Return EW (Selected Period) =
VAR CurrentDate = MAX(fct_signal_daily[date_t])
RETURN
    PRODUCTX(
        FILTER(
            ALLSELECTED(fct_signal_daily[date_t]),
            fct_signal_daily[date_t] <= CurrentDate
        ),
        1 + CALCULATE(MAX(fct_signal_daily[long_short_return_ew]))
    ) - 1
```
