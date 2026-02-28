import pandas as pd
import statsmodels.formula.api as smf
import duckdb

# ── 1. Load data ──────────────────────────────────────────────────────────────
con = duckdb.connect("equity_sentiment/dev.duckdb")
df = con.execute("""
    SELECT
        ticker,
        date_t,
        z_sentiment,
        weighted_sentiment,
        news_count,
        volume,
        forward_return_1d
    FROM fct_signal_panel
    WHERE forward_return_1d IS NOT NULL
""").df()
con.close()

df = df.dropna(subset=["z_sentiment", "forward_return_1d"])
df["date_t"] = df["date_t"].astype(str)

print(f"Panel shape: {df.shape}")
print(f"Date range: {df['date_t'].min()} → {df['date_t'].max()}")
print(f"Unique tickers: {df['ticker'].nunique()}\n")


# ── 2. Correlation ────────────────────────────────────────────────────────────
print("=" * 50)
print("STEP 1 — CORRELATION")
print("=" * 50)
corr = df[["z_sentiment", "weighted_sentiment", "forward_return_1d"]].corr()
print(corr[["forward_return_1d"]])
print()


# ── 3. Quintile Sort ──────────────────────────────────────────────────────────
print("=" * 50)
print("STEP 2 — QUINTILE SORT")
print("=" * 50)
df["quintile"] = pd.qcut(df["z_sentiment"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])

quintile_returns = (
    df.groupby("quintile", observed=True)["forward_return_1d"]
      .agg(avg_forward_return="mean", n="count")
)
print(quintile_returns)

q1 = quintile_returns.loc["Q1", "avg_forward_return"]
q5 = quintile_returns.loc["Q5", "avg_forward_return"]
print(f"\nQ5 - Q1 spread: {q5 - q1:.6f} ({(q5 - q1) * 100:.4f}%)\n")


# ── 4. Regression ─────────────────────────────────────────────────────────────
print("=" * 50)
print("STEP 3 — REGRESSION (date FE + clustered SE)")
print("=" * 50)
model = smf.ols(
    "forward_return_1d ~ z_sentiment + C(date_t)",
    data=df
).fit(
    cov_type="cluster",
    cov_kwds={"groups": df["date_t"]}
)

coef  = model.params["z_sentiment"]
tstat = model.tvalues["z_sentiment"]
pval  = model.pvalues["z_sentiment"]
print(f"β (z_sentiment) : {coef:.6f}")
print(f"t-stat           : {tstat:.4f}")
print(f"p-value          : {pval:.4f}")
print(f"R²               : {model.rsquared:.4f}\n")


# ── 5. Verdict ────────────────────────────────────────────────────────────────
print("=" * 50)
print("VERDICT")
print("=" * 50)
returns = quintile_returns["avg_forward_return"].tolist()
monotonic = all(returns[i] <= returns[i + 1] for i in range(len(returns) - 1))

print(f"Monotonic quintile pattern : {'✅ YES' if monotonic else '❌ NO'}")
print(f"β sign positive            : {'✅ YES' if coef > 0 else '❌ NO'}")
print(f"t-stat > 1.8               : {'✅ YES' if abs(tstat) > 1.8 else '❌ NO'}")

if monotonic and coef > 0 and abs(tstat) > 1.8:
    print("\n→ Signal looks promising. Dashboard is justified.")
elif monotonic or coef > 0:
    print("\n→ Weak signal. Dashboard is descriptive only.")
else:
    print("\n→ No signal found. Reconsider data or methodology.")