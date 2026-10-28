"""
compare_portfolio_transaction_ledger.py

TRANSACTION LEDGER version + CURRENCY-CONVERSION FEE + AUTOMATIC CASH
(cash remainder + actual dividends, each dated on its actual payment day).

Why it is structured this way:

Previously, dividends were calculated separately as a single number at the
moment the script was run. That meant the number changed every time the
script was run on a different day, and there was no way to know "how much
the portfolio held in accumulated dividends on September 25" once that
date had passed.

The solution: every dividend paid by every ETF becomes a "CASH" transaction
dated on its actual payment day (for the amount corresponding to how many
shares were held THAT day). Because the portfolio value is calculated day
by day with a cumulative sum (cumsum), a dividend paid on September 10
never affects the value on September 5 — so the same script can be used to
query ANY past cutoff date (August 25, September 17, September 25, today)
without needing a different "frozen" version for each report.

Project: capital markets analysis (simulated ETF portfolio)
"""

import os

import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date, timedelta

os.makedirs("outputs", exist_ok=True)

# ---------------------------------------------------------------
# 1. BASE TRANSACTION LEDGER (purchases, sales, and the manual cash
#    remainder after the SPY -> SCHD swap)
# ---------------------------------------------------------------
#   POSITIVE quantity -> purchase / cash inflow
#   NEGATIVE quantity -> sale
#
# The special ticker "CASH" represents uninvested cash — its "price" is
# always 1.00 and never changes (it earns no return).
# Dividends are NOT written here by hand — the script adds them
# automatically further below (section 3.2), dated on their actual
# payment day.

transactions = [
    # --- Portfolio opening: August 25, 2026 ---
    {"date": "2026-08-25", "ticker": "SPY",  "quantity": 20,  "price": 763.47},
    {"date": "2026-08-25", "ticker": "VTI",  "quantity": 27,  "price": 377.07},
    {"date": "2026-08-25", "ticker": "MAGS", "quantity": 119, "price": 67.20},
    {"date": "2026-08-25", "ticker": "IWM",  "quantity": 17,  "price": 297.97},
    {"date": "2026-08-25", "ticker": "XLK",  "quantity": 44,  "price": 180.05},
    {"date": "2026-08-25", "ticker": "SOXX", "quantity": 20,  "price": 506.18},
    {"date": "2026-08-25", "ticker": "XLV",  "quantity": 46,  "price": 174.70},
    {"date": "2026-08-25", "ticker": "XLE",  "quantity": 127, "price": 63.11},
    {"date": "2026-08-25", "ticker": "KBWB", "quantity": 52,  "price": 96.15},
    {"date": "2026-08-25", "ticker": "GLD",  "quantity": 19,  "price": 426.69},
    {"date": "2026-08-25", "ticker": "COPX", "quantity": 53,  "price": 94.53},
    {"date": "2026-08-25", "ticker": "ILF",  "quantity": 144, "price": 34.77},
    {"date": "2026-08-25", "ticker": "IBIT", "quantity": 112, "price": 44.64},
    {"date": "2026-09-17", "ticker": "SPY",  "quantity": -20, "price": 762.00},
    {"date": "2026-09-17", "ticker": "SCHD", "quantity": 449, "price": 33.90},

    # --- Cash remainder after the SPY -> SCHD swap (Sep 17, 2026) ---
    {"date": "2026-09-17", "ticker": "CASH", "quantity": 18.90, "price": 1.00},

    # --- Example of a future rebalancing (uncomment and edit when it happens) ---
    # {"date": "2026-09-15", "ticker": "XLE", "quantity": -127, "price": 61.00},
    # {"date": "2026-09-15", "ticker": "TIP", "quantity": 40,   "price": 110.50},
]

opening_date = "2026-08-25"
end_date     = (date.today() + timedelta(days=1)).isoformat()  # one day AFTER today (yfinance "end" is exclusive)

# Cutoff date to report (for reports, e.g. the close of a month). If left
# as None, the report only shows today's figures.
report_date = "2026-09-25"

# ---------------------------------------------------------------
# 1.1 CURRENCY-CONVERSION COSTS (Global66)
# ---------------------------------------------------------------
# Transfer assumed to be ordered on Aug 20, 2026 (Thursday), with 3 business
# days of delivery to IBKR (Fri 21, Mon 24, Tue 25) -> the money arrives
# exactly on Aug 25, 2026, so the opening date and positions do not change.
#
# Rate applied by Global66 that day (NOT the official TRM). It is only used
# to express the capital in pesos; in dollars the rate cancels out.
global66_entry_rate = 3074.50   # COP per USD — Global66 rate, Aug 20, 2026

# Global66 shows the fee as an "exchange-rate cost" (no additional operating
# costs), calculated on the amount sent in pesos.
# Quote of Oct 15, 2026 for an amount of ~USD 100,000 (sending
# COP 322,000,000 -> receiving USD 100,018.58): cost COP 4,508,000 = 1.4%.
# Note: a quote on Oct 9, 2026 showed 0.4% for a similar amount and could not
# be reproduced; the platform's fee varies, so the one observed on Oct 15 is
# adopted for the portfolio's amount (it also matches the rate used in the
# original opening).
conversion_fee_pct = 0.014   # 1.4% — Global66 fee on the amount sent

# ---------------------------------------------------------------
# 2. BASE CAPITAL (invested in the market + conversion fee)
# ---------------------------------------------------------------
base_transactions_df = pd.DataFrame(transactions)
base_transactions_df["date"] = pd.to_datetime(base_transactions_df["date"])

capital_invested_in_market = (
    base_transactions_df[base_transactions_df["date"] == pd.Timestamp(opening_date)]
    .apply(lambda row: row["quantity"] * row["price"], axis=1)
    .sum()
)

# Method B (agreed): the fee was deducted on the peso side BEFORE converting
# — the actual amount disbursed is reconstructed by dividing by
# (1 - fee), not by adding the fee on top of the already-net capital.
capital_with_conversion_fee = capital_invested_in_market / (1 - conversion_fee_pct)
conversion_fee_paid_usd = capital_with_conversion_fee - capital_invested_in_market

# 4x1000 (GMF — Gravamen a los Movimientos Financieros, Colombia's financial
# transactions tax, 0.4%): charged on the peso amount leaving the bank
# account toward Global66 — that is, on the capital ALREADY INCLUDING the
# conversion fee. It is a State tax, independent of Global66. Since it is a
# direct percentage and is converted at the same rate both to pesos and back
# to dollars, the rate cancels algebraically — the net effect is equivalent
# to multiplying the capital (already with the fee) by 1.004.
gmf_pct = 0.004
actual_capital_disbursed = capital_with_conversion_fee * (1 + gmf_pct)
gmf_paid_usd = actual_capital_disbursed - capital_with_conversion_fee

initial_value = actual_capital_disbursed

# Actual capital disbursed expressed in pesos, at the Global66 rate
actual_capital_disbursed_cop = actual_capital_disbursed * global66_entry_rate

# ---------------------------------------------------------------
# 3. DOWNLOAD PRICES FOR THE REAL TICKERS (excluding CASH, which is not traded)
# ---------------------------------------------------------------
real_tickers = [t for t in base_transactions_df["ticker"].unique() if t != "CASH"]

historical_prices = yf.download(
    real_tickers,
    start=opening_date,
    end=end_date
)["Close"]
historical_prices = historical_prices.ffill()

# ---------------------------------------------------------------
# 3.1 "PASS 1" POSITIONS — only to know how many shares were held
#     on each actual dividend payment date (not the final result)
# ---------------------------------------------------------------
base_movements = base_transactions_df.pivot_table(
    index="date", columns="ticker", values="quantity", aggfunc="sum"
)
base_movements = base_movements.reindex(historical_prices.index, fill_value=0)
pass1_positions = base_movements.fillna(0).cumsum()

def quantity_on_date(positions_table, on_date, ticker):
    """Quantity of a ticker on a given date; if the date is not a market
    business day, uses the nearest prior position in force."""
    if on_date in positions_table.index:
        return positions_table.loc[on_date, ticker]
    earlier = positions_table.index[positions_table.index <= on_date]
    if len(earlier) == 0:
        return 0.0
    return positions_table.loc[earlier[-1], ticker]

# ---------------------------------------------------------------
# 3.2 GENERATE AUTOMATIC "CASH" TRANSACTIONS FOR EACH ACTUAL DIVIDEND
# ---------------------------------------------------------------
dividend_transactions = []
dividend_detail = []   # one record per dividend, for the per-position table

for ticker in real_tickers:
    dividend_series = yf.Ticker(ticker).dividends
    if dividend_series.empty:
        continue

    dividend_series.index = dividend_series.index.tz_localize(None)
    period_dividends = dividend_series[
        (dividend_series.index >= pd.Timestamp(opening_date)) &
        (dividend_series.index <= pd.Timestamp(date.today()))
    ]

    for payment_date, dividend_per_share in period_dividends.items():
        quantity_that_day = quantity_on_date(pass1_positions, payment_date, ticker)
        amount = quantity_that_day * dividend_per_share
        if amount > 0:
            # Anchor the transaction to an actual business day of the price
            # calendar — if the payment fell on a weekend/holiday, the
            # reindex in section 4 would silently drop it.
            business_days_up_to_payment = historical_prices.index[historical_prices.index <= payment_date]
            transaction_date = (
                business_days_up_to_payment[-1] if len(business_days_up_to_payment) > 0
                else historical_prices.index[0]
            )
            dividend_transactions.append({
                "date": transaction_date.date().isoformat(),
                "ticker": "CASH",
                "quantity": round(float(amount), 4),
                "price": 1.00,
            })
            dividend_detail.append({
                "ticker": ticker,
                "payment_date": payment_date.date().isoformat(),
                "transaction_date": transaction_date.date().isoformat(),
                "dividend_per_share": float(dividend_per_share),
                "shares": float(quantity_that_day),
                "amount_usd": round(float(amount), 4),
            })

total_dividends_usd = sum(t["quantity"] for t in dividend_transactions)

# ---------------------------------------------------------------
# 3.3 COMPLETE TRANSACTION LEDGER (base + automatic dividends)
# ---------------------------------------------------------------
all_transactions = transactions + dividend_transactions
transactions_df = pd.DataFrame(all_transactions)
transactions_df["date"] = pd.to_datetime(transactions_df["date"])

# Add the CASH column (fixed price $1.00) to the historical prices
historical_prices["CASH"] = 1.00

# ---------------------------------------------------------------
# 3.4 AVERAGE PURCHASE COST PER TICKER (for individual returns)
# ---------------------------------------------------------------
purchases = transactions_df[transactions_df["quantity"] > 0].copy()
purchases["total_cost"] = purchases["quantity"] * purchases["price"]
avg_purchase_cost = (
    purchases.groupby("ticker")
    .apply(lambda g: g["total_cost"].sum() / g["quantity"].sum())
)

# ---------------------------------------------------------------
# 4. FINAL RECONSTRUCTION — how many shares/cash were held each day
# ---------------------------------------------------------------
movements = transactions_df.pivot_table(
    index="date", columns="ticker", values="quantity", aggfunc="sum"
)
movements = movements.reindex(historical_prices.index, fill_value=0)
daily_positions = movements.fillna(0).cumsum()
daily_positions = daily_positions[historical_prices.columns]

# ---------------------------------------------------------------
# 5. PORTFOLIO VALUE EACH DAY (already includes CASH: remainder + dividends)
# ---------------------------------------------------------------
daily_portfolio_value = (historical_prices * daily_positions).sum(axis=1)

daily_portfolio_return = (daily_portfolio_value / initial_value - 1) * 100
portfolio_return_today = daily_portfolio_return.iloc[-1]
current_value = daily_portfolio_value.iloc[-1]

# ---------------------------------------------------------------
# 6. BENCHMARK — S&P 500
# ---------------------------------------------------------------
benchmark = yf.download(
    "^GSPC",
    start=opening_date,
    end=end_date
)["Close"].squeeze()

daily_gspc_return = (benchmark / benchmark.iloc[0] - 1) * 100
gspc_return_today = daily_gspc_return.iloc[-1]

# ---------------------------------------------------------------
# 6.1 TOTAL-RETURN BENCHMARK (dividends reinvested)
# ---------------------------------------------------------------
# ^GSPC is a PRICE index: it does not include dividends. The professional
# standard for measuring performance is total return (dividends
# reinvested). The official ^SP500TR index is tried first; if Yahoo does not
# provide it for these dates, SPY with dividend-adjusted prices
# (auto_adjust=True) is used as an approximation. The script prints which
# of the two was used.
def download_total_return():
    candidates = (
        ("^SP500TR", "S&P 500 Total Return (^SP500TR)"),
        ("SPY",      "SPY adjusted for dividends (total-return approximation)"),
    )
    for tr_ticker, label in candidates:
        try:
            series = yf.download(
                tr_ticker, start=opening_date, end=end_date,
                auto_adjust=True, progress=False
            )["Close"].squeeze().dropna()
        except Exception:
            continue
        if len(series) >= 2 and series.index[0] == benchmark.index[0]:
            series = series.reindex(benchmark.index).ffill()
            return series, label, tr_ticker
    return None, None, None

total_return_benchmark, total_return_label, total_return_ticker_used = download_total_return()
has_total_return = total_return_benchmark is not None
if has_total_return:
    daily_sp500tr_return = (total_return_benchmark / total_return_benchmark.iloc[0] - 1) * 100
    sp500tr_return_today = daily_sp500tr_return.iloc[-1]
    print(f"\nTotal-return benchmark used: {total_return_label}")
else:
    print("\n⚠️  Could not download a total-return benchmark (neither ^SP500TR nor SPY); "
          "only the ^GSPC price index is shown.")

# ---------------------------------------------------------------
# 7. RESULTS — TODAY
# ---------------------------------------------------------------
days_elapsed = (date.today() - pd.Timestamp(opening_date).date()).days
months_elapsed = days_elapsed / 30.44

print("=" * 60)
print("PERFORMANCE COMPARISON — TODAY")
print(f"Period: {opening_date} to today")
print(f"Days elapsed: {days_elapsed} days ({months_elapsed:.1f} months)")
print("=" * 60)
print(f"Capital invested in the market:          ${capital_invested_in_market:,.2f}")
print(f"Conversion fee (Global66 {conversion_fee_pct*100:.1f}%):       ${conversion_fee_paid_usd:,.2f}")
print(f"4x1000 tax (GMF {gmf_pct*100:.1f}%):                  ${gmf_paid_usd:,.2f}")
print(f"Actual capital disbursed:                ${actual_capital_disbursed:,.2f}")
print(f"  equivalent in pesos (Global66 rate {global66_entry_rate:,.2f}): ${actual_capital_disbursed_cop:,.2f} COP")
print(f"Dividends accumulated to date:           ${total_dividends_usd:,.2f}")
print("-" * 60)
print(f"Current portfolio value:  ${current_value:,.2f}")
print("-" * 60)
print(f"ETFs:   {portfolio_return_today:>7.2f}%")
print(f"S&P 500 (GSPC, price):           {gspc_return_today:>7.2f}%")
if has_total_return:
    print(f"S&P 500 total return ({total_return_ticker_used}): {sp500tr_return_today:>7.2f}%")
print("=" * 60)
print(f"\nDifference vs S&P 500 (price):          {portfolio_return_today - gspc_return_today:+.2f} points")
if has_total_return:
    print(f"Difference vs S&P 500 (total return):   {portfolio_return_today - sp500tr_return_today:+.2f} points")


def positions_table_on(on_date):
    """Builds the positions table (quantity, price, value, weight,
    return) as it stood on a specific date."""
    date_ts = pd.Timestamp(on_date)
    if date_ts not in daily_positions.index:
        raise ValueError(f"{on_date} is not a market business day in the downloaded range.")

    pos = daily_positions.loc[date_ts]
    prices = historical_prices.loc[date_ts]
    total_value = (pos * prices).sum()

    table = pd.DataFrame({"quantity": pos, "price": prices, "value": pos * prices})
    table = table[table["quantity"] != 0]
    table["weight_%"] = (table["value"] / total_value) * 100
    table["purchase_price"] = avg_purchase_cost.reindex(table.index)
    table["return_%"] = (table["price"] / table["purchase_price"] - 1) * 100
    return table.sort_values("weight_%", ascending=False), total_value


def print_table(table, label):
    print(f"\nPositions ({len(table)}) — {label}:")
    print(table[["quantity", "price", "value", "weight_%", "return_%"]].to_string(
        formatters={
            "quantity": "{:.2f}".format,
            "price": "${:,.2f}".format,
            "value": "${:,.2f}".format,
            "weight_%": "{:.2f}%".format,
            "return_%": "{:+.2f}%".format,
        }
    ))


def print_dividends(up_to, label):
    """Dividends per position up to a date (inclusive): detail per payment
    and total per ETF."""
    if not dividend_detail:
        print(f"\nDividends — {label}: none in the period.")
        return 0.0
    df = pd.DataFrame(dividend_detail)
    df = df[pd.to_datetime(df["transaction_date"]) <= pd.Timestamp(up_to)]
    if df.empty:
        print(f"\nDividends — {label}: none in the period.")
        return 0.0

    print(f"\nDividends per payment — {label}:")
    detail = df.sort_values(["ticker", "payment_date"])
    print(detail[["ticker", "payment_date", "dividend_per_share", "shares", "amount_usd"]].to_string(
        index=False,
        formatters={
            "dividend_per_share": "${:,.4f}".format,
            "shares": "{:,.2f}".format,
            "amount_usd": "${:,.2f}".format,
        }
    ))

    summary = df.groupby("ticker")["amount_usd"].sum().sort_values(ascending=False)
    total = summary.sum()
    print(f"\nTotal dividends per position — {label}:")
    for t, m in summary.items():
        print(f"  {t:<6} ${m:>10,.2f}   ({m / total * 100:>5.1f}% of total)")
    print(f"  {'TOTAL':<6} ${total:>10,.2f}")
    return total


table_today, _ = positions_table_on(historical_prices.index[-1])
print_table(table_today, "today")
print_dividends(historical_prices.index[-1], "accumulated to date")

# ---------------------------------------------------------------
# 7.1 RESULTS ON A SPECIFIC CUTOFF DATE (for reports)
# ---------------------------------------------------------------
if report_date is not None:
    report_date_ts = pd.Timestamp(report_date)
    if report_date_ts in daily_portfolio_value.index:
        value_at_cutoff = daily_portfolio_value.loc[report_date_ts]
        return_at_cutoff = daily_portfolio_return.loc[report_date_ts]
        gspc_return_at_cutoff = daily_gspc_return.loc[report_date_ts]
        days_to_cutoff = (report_date_ts.date() - pd.Timestamp(opening_date).date()).days

        print("\n" + "=" * 60)
        print(f"PERFORMANCE COMPARISON — CUTOFF OF {report_date}")
        print(f"Days elapsed to that date: {days_to_cutoff} days ({days_to_cutoff/30.44:.1f} months)")
        print("=" * 60)
        print(f"Portfolio value on that date: ${value_at_cutoff:,.2f}")
        print(f"ETFs:   {return_at_cutoff:>7.2f}%")
        print(f"S&P 500 (GSPC, price):           {gspc_return_at_cutoff:>7.2f}%")
        print(f"Difference vs S&P 500 (price):          {return_at_cutoff - gspc_return_at_cutoff:+.2f} points")
        if has_total_return:
            sp500tr_return_at_cutoff = daily_sp500tr_return.loc[report_date_ts]
            print(f"S&P 500 total return ({total_return_ticker_used}): {sp500tr_return_at_cutoff:>7.2f}%")
            print(f"Difference vs S&P 500 (total return):   {return_at_cutoff - sp500tr_return_at_cutoff:+.2f} points")

        # Reference: portfolio BEFORE entry costs (fee + GMF), measured
        # against the capital invested in the market
        return_before_costs = (value_at_cutoff / capital_invested_in_market - 1) * 100
        print(f"\nPortfolio before entry costs (vs capital invested ${capital_invested_in_market:,.2f}): {return_before_costs:+.2f}%")
        print(f"  vs S&P 500 price:          {return_before_costs - gspc_return_at_cutoff:+.2f} points")
        if has_total_return:
            print(f"  vs S&P 500 total return:   {return_before_costs - sp500tr_return_at_cutoff:+.2f} points")

        table_at_cutoff, _ = positions_table_on(report_date_ts)
        print_table(table_at_cutoff, f"at the close of {report_date}")
        print_dividends(report_date_ts, f"up to the cutoff of {report_date}")
    else:
        print(f"\n⚠️  {report_date} is not yet available in the downloaded data "
              f"(is it a future date or a non-business day?).")

# ---------------------------------------------------------------
# 7.2 CHART TRIMMED TO THE CUTOFF DATE (for the report)
# ---------------------------------------------------------------
if report_date is not None and report_date_ts in daily_portfolio_value.index:
    in_range = daily_gspc_return.index <= report_date_ts

    plt.figure(figsize=(10, 6))
    plt.plot(daily_gspc_return.index[in_range], daily_gspc_return[in_range],
              label="S&P 500 (price)", linewidth=2, color="steelblue", marker="o")
    if has_total_return:
        plt.plot(daily_sp500tr_return.index[in_range], daily_sp500tr_return[in_range],
                  label="S&P 500 total return", linewidth=2, color="darkorange",
                  linestyle="--", marker="o")
    plt.plot(daily_portfolio_return.index[in_range], daily_portfolio_return[in_range],
              label="ETFs", linewidth=2, color="green", marker="o")
    plt.title(f"Comparative return — {opening_date} to {report_date}")
    plt.xlabel("Date")
    plt.ylabel("Return (%)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"outputs/portfolio_comparison_cutoff_{report_date}.png", dpi=150)
    print(f"\n✅ Cutoff chart saved to outputs/portfolio_comparison_cutoff_{report_date}.png")

# ---------------------------------------------------------------
# 8. CHART — FULL SERIES, DAY BY DAY
# ---------------------------------------------------------------
plt.figure(figsize=(10, 6))

plt.plot(daily_gspc_return.index, daily_gspc_return,
         label="S&P 500 (price)", linewidth=2, color="steelblue", marker="o")

if has_total_return:
    plt.plot(daily_sp500tr_return.index, daily_sp500tr_return,
             label="S&P 500 total return", linewidth=2, color="darkorange",
             linestyle="--", marker="o")

plt.plot(daily_portfolio_return.index, daily_portfolio_return,
         label="ETFs", linewidth=2, color="green", marker="o")

plt.title(f"Comparative return since {opening_date}")
plt.xlabel("Date")
plt.ylabel("Return (%)")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()

plt.savefig("outputs/portfolio_comparison.png", dpi=150)
print("\n✅ Chart saved to outputs/portfolio_comparison.png")

plt.show()