"""
tnx_and_historical_analysis.py

STANDALONE, ONE-OFF SCRIPT to feed the Executive Report for the September 25,
2026 cutoff. It is not part of the portfolio's daily tracking system.

It generates two pieces of evidence:

1. The movement of ^TNX (10-year Treasury yield) during the evaluated month
   (Aug 25, 2026 to Sep 25, 2026) — to explain the macro context behind the
   performance of GLD, COPX, KBWB and XLE.

2. A table with the HISTORICAL performance (prior to the portfolio opening)
   of the 13 original positions, over the horizon used to verify that they
   were "winning positions" before including them: 5 years for most, 3 years
   for MAGS and 2 years for IBIT (because they have traded for a shorter
   time) — compared against the S&P 500 over that same horizon.

   The ETFs are measured in TOTAL RETURN (dividends reinvested, auto_adjust=True), 
   so the benchmark must also be total return(^SP500TR).  
   This version shows Index Price (^GSPC) and Total Return (^SP500TR) benchmarks, 
   but the "beat" column is calculated against total return.

Project: capital markets analysis (simulated ETF portfolio)
"""

import yfinance as yf
import pandas as pd

# ---------------------------------------------------------------
# 1. ^TNX PERFORMANCE DURING THE EVALUATED MONTH
# ---------------------------------------------------------------
portfolio_opening_date = "2026-08-25"
cutoff_date = "2026-09-25"
download_until_date = "2026-09-26"  # one day after the cutoff (yfinance "end" is exclusive)

tnx = yf.download(
    "^TNX",
    start=portfolio_opening_date,
    end=download_until_date
)["Close"].squeeze()

tnx_start = tnx.iloc[0]
tnx_end = tnx.loc[pd.Timestamp(cutoff_date)] if pd.Timestamp(cutoff_date) in tnx.index else tnx.iloc[-1]

change_points = tnx_end - tnx_start
change_bp = change_points * 100   # 1 percentage point = 100 basis points
relative_change_pct = (tnx_end / tnx_start - 1) * 100

print("=" * 60)
print("^TNX MOVEMENT DURING THE EVALUATED PERIOD")
print(f"Period: {portfolio_opening_date} to {cutoff_date}")
print("=" * 60)
print(f"^TNX on {portfolio_opening_date}: {tnx_start:.4f}%")
print(f"^TNX on {cutoff_date}:        {tnx_end:.4f}%")
print(f"Change in percentage points: {change_points:+.4f} pp")
print(f"Change in basis points:      {change_bp:+.1f} bp")
print(f"Relative percentage change:  {relative_change_pct:+.2f}%")

# ---------------------------------------------------------------
# 2. HISTORICAL PERFORMANCE OF THE 13 ORIGINAL POSITIONS
#    (verification of "winning position" BEFORE including it)
# ---------------------------------------------------------------
# Verification horizon per position, depending on how long MAGS and IBIT
# have been trading (both are recent ETFs).
original_positions = {
    "SPY":  5, "VTI": 5, "IWM": 5, "XLK": 5, "SOXX": 5, "XLV": 5,
    "XLE":  5, "KBWB": 5, "GLD": 5, "COPX": 5, "ILF": 5,
    "MAGS": 3,
    "IBIT": 2,
}

historical_end_date = pd.Timestamp(portfolio_opening_date)  # Aug 25, 2026


def download_total_return_benchmark(start, end):
    """S&P 500 total return: first the official ^SP500TR index; if Yahoo
    does not provide it for that range, SPY with adjusted prices
    (approximation). Returns (series, ticker_used)."""
    for tr_ticker in ("^SP500TR", "SPY"):
        try:
            series = yf.download(tr_ticker, start=start, end=end,
                                 auto_adjust=True, progress=False)["Close"].squeeze().dropna()
        except Exception:
            continue
        if len(series) >= 2:
            return series, tr_ticker
    raise RuntimeError(f"Could not download a total-return benchmark for {start} to {end}")


results = []

for ticker, horizon_years in original_positions.items():
    historical_start_date = historical_end_date - pd.DateOffset(years=horizon_years)

    # auto_adjust=True (yfinance default) already incorporates dividends
    # and splits -> this is TOTAL RETURN, not just price change.
    prices = yf.download(
        ticker,
        start=historical_start_date.strftime("%Y-%m-%d"),
        end=(historical_end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True
    )["Close"].squeeze()

    total_return_pct = (prices.iloc[-1] / prices.iloc[0] - 1) * 100

    start_str = historical_start_date.strftime("%Y-%m-%d")
    end_str = (historical_end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # S&P 500 over the SAME horizon: PRICE index (reference) ...
    sp500_price = yf.download(
        "^GSPC", start=start_str, end=end_str, auto_adjust=True, progress=False
    )["Close"].squeeze()
    sp500_price_return_pct = (sp500_price.iloc[-1] / sp500_price.iloc[0] - 1) * 100

    # ... and TOTAL RETURN (the correct benchmark to compare against the ETFs)
    sp500_tr, tr_ticker_used = download_total_return_benchmark(start_str, end_str)
    sp500_return_pct = (sp500_tr.iloc[-1] / sp500_tr.iloc[0] - 1) * 100

    results.append({
        "ticker": ticker,
        "horizon_years": horizon_years,
        "start_date": historical_start_date.date().isoformat(),
        "end_date": historical_end_date.date().isoformat(),
        "total_return_%": round(total_return_pct, 2),
        "sp500_price_%": round(sp500_price_return_pct, 2),
        "sp500_total_return_%": round(sp500_return_pct, 2),
        "benchmark_tr": tr_ticker_used,
        "beat_sp500_tr": total_return_pct > sp500_return_pct,
        "beat_price_index": total_return_pct > sp500_price_return_pct,
    })

historical_table = pd.DataFrame(results).sort_values("total_return_%", ascending=False)

print("\n" + "=" * 90)
print("HISTORICAL PERFORMANCE OF THE 13 ORIGINAL POSITIONS (prior to the portfolio opening)")
print("=" * 90)
print(historical_table.to_string(index=False, formatters={
    "total_return_%": "{:+.2f}%".format,
    "sp500_price_%": "{:+.2f}%".format,
    "sp500_total_return_%": "{:+.2f}%".format,
}))

count_beat = historical_table["beat_sp500_tr"].sum()
count_beat_price = historical_table["beat_price_index"].sum()
print(f"\n{count_beat} of {len(historical_table)} positions outperformed the TOTAL RETURN S&P 500 over their respective verification horizon.")
print(f"(With the earlier comparison, against the ^GSPC price index, it was {count_beat_price} of {len(historical_table)}.)")
print("Positions whose result changes when using total return:",
      historical_table.loc[historical_table["beat_sp500_tr"] != historical_table["beat_price_index"], "ticker"].tolist())