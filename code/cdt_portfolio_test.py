"""
cdt_portfolio_test.py

INDEPENDENT PORTFOLIO — "Would my portfolio have paid the same as a CDT?"
(A CDT is a Colombian fixed-term deposit.)

Answers the question a conservative, income-oriented investor would ask
(priority: capital preservation and a steady monthly income):
"If, instead of investing in a CDT (13% E.A., with monthly interest
withdrawal), I had invested in this ETF portfolio, would I have been able
to withdraw that same amount of pesos every month WITHOUT TOUCHING the
original capital?"

The uninvested cash (remainder from the SPY -> SCHD swap + dividends
received) is treated like one more position, with ticker "CASH" and a
fixed price of $1.00, generated automatically from real dated events (each
dividend on its actual payment day).

Fees and exchange rates (actual Global66 quotes, not the official TRM):
Global66 applies its own rate depending on the amount and the direction
(buying or selling USD), and shows its fee as an "exchange-rate cost".
  - ENTRY: 1.4% fee on the amount sent (platform quote for ~USD 100,000) and
    the Global66 rate of Aug 20, 2026 (transfer assumed that day; 3 business
    days of delivery to IBKR -> arrives Aug 25, the opening date).
  - EXIT: 3% fee for amounts between USD 950 and 1,000 and the Global66 rate
    of the cutoff day. For small amounts, delivery in pesos is the same day.
    Global66 changes its fees by day and by amount range, so this is a
    documented assumption of the exercise.
  - The GMF (4x1000, Colombia's financial transactions tax) is a State tax,
    independent of Global66.
  - The dividend detail per position is reported.

Rules of the experiment (agreed before writing the code):

1. Target amount = interest that a Colombian CDT at 13% E.A. would pay on
   the ACTUAL capital disbursed by the investor (includes the Global66
   conversion fee of 1.4% + the 4x1000 tax / GMF of 0.4%), converted to
   pesos at the Global66 entry rate (Aug 20, 2026).

2. To cover the target amount, the following order is used: first the cash
   already available in the account (remainder + accumulated dividends); if
   that is not enough, part of the WINNING position with the highest
   percentage return is sold (and the next one in the ranking if still
   needed).

3. Exit fee (Global66, USD->COP, 3% for amounts of USD 950 to 1,000,
   deducted from the dollar amount before converting): the USD amount to
   extract is "grossed up" so that, after subtracting this fee, the net in
   pesos reaches or exceeds the CDT target.

4. HARD CONDITION: the portfolio value after withdrawing the total amount
   (available cash + sale) can never fall below the actual capital
   disbursed in USD. If it is not met, no sale is executed that month.

5. Portfolio INDEPENDENT of the main one — it starts with the same
   composition, but every sale this experiment executes is recorded only in
   its own transaction ledger.

6. Positions at a loss are never liquidated under any circumstances.

Project: capital markets analysis (simulated ETF portfolio)
"""

import yfinance as yf
import pandas as pd
from datetime import date
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# =================================================================
# 1. TRANSACTION LEDGER OF THIS PORTFOLIO (INDEPENDENT)
# =================================================================
# Dividends are NOT written here by hand — the script adds them
# automatically further below (section 6), dated on their actual payment
# day, just like in the main script.

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

    # --- Sales / withdrawals executed by the CDT experiment (added here,
    #     month by month, only if the hard condition is met) ---
    # {"date": "2026-09-25", "ticker": "SOXX", "quantity": -1.24, "price": 572.66},
    # {"date": "2026-09-25", "ticker": "CASH", "quantity": -269.47, "price": 1.00},
]

# =================================================================
# 2. PARAMETERS OF THE MONTH TO EVALUATE — ADJUST EVERY TIME IT IS RUN
# =================================================================
portfolio_opening_date = "2026-08-25"
period_start_date      = "2026-08-25"
cutoff_date            = "2026-09-25"
download_until_date    = "2026-09-26"   # one day after cutoff_date (yfinance "end" is exclusive)

# Global66 rates (NOT the official TRM)
global66_entry_rate = 3074.50   # COP/USD, Aug 20, 2026 (assumed transfer; arrives Aug 25). Fixed.
global66_exit_rate  = 3329.61   # COP/USD, cutoff day (selling USD) <-- update every month

cdt_annual_rate = 0.13
cdt_monthly_rate = (1 + cdt_annual_rate) ** (1/12) - 1   # ≈ 1.0237%

entry_fee_pct = 0.014   # Global66, COP -> USD, Method B (divide): sent = net / (1 - fee)
gmf_pct       = 0.004   # 4x1000 / GMF — State tax, independent of Global66
exit_fee_pct  = 0.03    # Global66, USD -> COP, "exchange-rate cost" on the USD amount

# Range of amounts (USD) for which the 3% exit fee was quoted (Oct 15, 2026).
exit_fee_range_usd = (950, 1000)

if global66_exit_rate is None:
    raise ValueError(
        "'global66_exit_rate' must be set to the Global66 rate of the cutoff day "
        "before running the script."
    )

# =================================================================
# 3. ACTUAL CAPITAL DISBURSED (entry)
# =================================================================
base_transactions_df = pd.DataFrame(transactions)
base_transactions_df["date"] = pd.to_datetime(base_transactions_df["date"])

capital_invested_in_market = (
    base_transactions_df[base_transactions_df["date"] == pd.Timestamp(portfolio_opening_date)]
    .apply(lambda row: row["quantity"] * row["price"], axis=1)
    .sum()
)

capital_with_entry_fee = capital_invested_in_market / (1 - entry_fee_pct)
entry_fee_usd = capital_with_entry_fee - capital_invested_in_market

actual_capital_disbursed = capital_with_entry_fee * (1 + gmf_pct)
gmf_paid_usd = actual_capital_disbursed - capital_with_entry_fee

initial_value_usd = actual_capital_disbursed

# =================================================================
# 4. DOWNLOAD PRICES FOR THE REAL TICKERS (excluding CASH, which is not traded)
# =================================================================
real_tickers = [t for t in base_transactions_df["ticker"].unique() if t != "CASH"]

historical_prices = yf.download(
    real_tickers,
    start=period_start_date,
    end=download_until_date
)["Close"]
historical_prices = historical_prices.ffill()

# =================================================================
# 5. "PASS 1" POSITIONS — only to know how many shares were held on
#    each actual dividend payment date (not the final result)
# =================================================================
base_movements = base_transactions_df.pivot_table(
    index="date", columns="ticker", values="quantity", aggfunc="sum"
)
base_movements = base_movements.reindex(historical_prices.index, fill_value=0)
pass1_positions = base_movements.fillna(0).cumsum()

def quantity_on_date(positions_table, on_date, ticker):
    if on_date in positions_table.index:
        return positions_table.loc[on_date, ticker]
    earlier = positions_table.index[positions_table.index <= on_date]
    if len(earlier) == 0:
        return 0.0
    return positions_table.loc[earlier[-1], ticker]

# =================================================================
# 6. GENERATE AUTOMATIC "CASH" TRANSACTIONS FOR EACH ACTUAL DIVIDEND
# =================================================================
dividend_transactions = []
dividend_detail = []   # one record per dividend, for the per-position table

for ticker in real_tickers:
    dividend_series = yf.Ticker(ticker).dividends
    if dividend_series.empty:
        continue

    dividend_series.index = dividend_series.index.tz_localize(None)
    period_dividends = dividend_series[
        (dividend_series.index >= pd.Timestamp(period_start_date)) &
        (dividend_series.index <= pd.Timestamp(cutoff_date))
    ]

    for payment_date, dividend_per_share in period_dividends.items():
        quantity_that_day = quantity_on_date(pass1_positions, payment_date, ticker)
        amount = quantity_that_day * dividend_per_share
        if amount > 0:
            # Anchor to an actual business day of the price calendar — if the
            # payment fell on a weekend/holiday, the later reindex would
            # silently drop it.
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
                "dividend_per_share": float(dividend_per_share),
                "shares": float(quantity_that_day),
                "amount_usd": round(float(amount), 4),
            })

total_dividends_usd = sum(t["quantity"] for t in dividend_transactions)

# =================================================================
# 7. COMPLETE TRANSACTION LEDGER (base + automatic dividends)
# =================================================================
all_transactions = transactions + dividend_transactions
transactions_df = pd.DataFrame(all_transactions)
transactions_df["date"] = pd.to_datetime(transactions_df["date"])

historical_prices["CASH"] = 1.00

purchases = transactions_df[transactions_df["quantity"] > 0].copy()
purchases["total_cost"] = purchases["quantity"] * purchases["price"]
avg_purchase_cost = (
    purchases.groupby("ticker")
    .apply(lambda g: g["total_cost"].sum() / g["quantity"].sum())
)

movements = transactions_df.pivot_table(
    index="date", columns="ticker", values="quantity", aggfunc="sum"
)
movements = movements.reindex(historical_prices.index, fill_value=0)
daily_positions = movements.fillna(0).cumsum()
daily_positions = daily_positions[historical_prices.columns]

cutoff_positions = daily_positions.loc[cutoff_date]
cutoff_prices = historical_prices.loc[cutoff_date]
held_positions = cutoff_positions[cutoff_positions != 0]

# TOTAL portfolio value on the cutoff date — NOW it does include the cash
# (remainder + dividends), just like Yahoo/IBKR.
portfolio_value_at_cutoff = (cutoff_positions * cutoff_prices).sum()

# Cash available WITHOUT selling anything — remainder + accumulated dividends
available_cash = cutoff_positions["CASH"] if "CASH" in cutoff_positions.index else 0.0

# =================================================================
# 8. INDIVIDUAL RETURN OF EACH POSITION (CASH stays at 0% and therefore
#    is never considered a "winner" to sell)
# =================================================================
table = pd.DataFrame({
    "quantity": held_positions,
    "cutoff_price": cutoff_prices.reindex(held_positions.index),
})
table["purchase_price"] = avg_purchase_cost.reindex(table.index)
table["return_%"] = (table["cutoff_price"] / table["purchase_price"] - 1) * 100
table["cutoff_value"] = table["quantity"] * table["cutoff_price"]
table["weight_%"] = (table["cutoff_value"] / portfolio_value_at_cutoff) * 100

# Full table for the report — all positions, ordered from largest to
# smallest weight (same format as the main portfolio)
report_table = table.sort_values("weight_%", ascending=False)

winners = table[(table["return_%"] > 0) & (table.index != "CASH")].sort_values(
    "return_%", ascending=False
)

# =================================================================
# 9. TARGET AMOUNT — WHAT THE CDT WOULD PAY THAT MONTH, IN PESOS
# =================================================================
reference_capital_cop = initial_value_usd * global66_entry_rate
target_amount_cop = reference_capital_cop * cdt_monthly_rate

# =================================================================
# 10. USD NEEDED (grossed up for the exit fee) AND SALES
# =================================================================
# USD needed = target_COP / (exit_rate x (1 - exit_fee))
total_usd_needed = target_amount_cop / (global66_exit_rate * (1 - exit_fee_pct))

if not (exit_fee_range_usd[0] <= total_usd_needed <= exit_fee_range_usd[1]):
    print(f"\n⚠️  The amount to extract (${total_usd_needed:,.2f}) is OUTSIDE the range "
          f"USD {exit_fee_range_usd[0]:,}–{exit_fee_range_usd[1]:,} for which the "
          f"{exit_fee_pct*100:.1f}% exit fee was quoted. Confirm the fee that applies to that amount.")

# The first thing used is the cash ALREADY AVAILABLE (remainder + dividends)
usd_shortfall = total_usd_needed - available_cash

proposed_sales = []   # (ticker, quantity_to_sell, usd_to_sell)
total_usd_sold = 0.0

if usd_shortfall > 0:
    for ticker, row in winners.iterrows():
        if usd_shortfall <= 0:
            break
        price = row["cutoff_price"]
        available_value_usd = row["cutoff_value"]
        usd_to_sell = min(usd_shortfall, available_value_usd)
        quantity_to_sell = usd_to_sell / price
        proposed_sales.append((ticker, quantity_to_sell, usd_to_sell))
        total_usd_sold += usd_to_sell
        usd_shortfall -= usd_to_sell

covered_with_sales = usd_shortfall <= 0.01

# =================================================================
# 11. THE HARD CONDITION
# =================================================================
# What LEAVES the portfolio is the TOTAL amount withdrawn (cash that was
# already available + what was just sold) — not only what was sold. The
# origin of the money (already in CASH, or generated by selling a position)
# does not change how much is withdrawn in total.
total_amount_withdrawn = available_cash + total_usd_sold  # == total_usd_needed if covered_with_sales
portfolio_value_after = portfolio_value_at_cutoff - total_amount_withdrawn
capital_not_affected = portfolio_value_after >= initial_value_usd

operation_is_executed = covered_with_sales and capital_not_affected

# Settlement to the investor
total_usd_extracted = total_amount_withdrawn
gross_cop = total_usd_extracted * global66_exit_rate
exit_fee_usd = total_usd_extracted * exit_fee_pct
net_cop_delivered = gross_cop * (1 - exit_fee_pct)

# =================================================================
# 12. RESULTS
# =================================================================
print("=" * 60)
print("TEST: WOULD THE PORTFOLIO HAVE PAID THE SAME AS A CDT?")
print(f"Period evaluated: {period_start_date} to {cutoff_date}")
print("=" * 60)

print(f"\n--- Actual capital disbursed (entry) ---")
print(f"Capital invested in the market:         ${capital_invested_in_market:,.2f}")
print(f"Conversion fee (Global66 {entry_fee_pct*100:.1f}%):      ${entry_fee_usd:,.2f}")
print(f"4x1000 tax (GMF {gmf_pct*100:.1f}%):                 ${gmf_paid_usd:,.2f}")
print(f"Actual capital disbursed:                ${actual_capital_disbursed:,.2f}")

print(f"\nPortfolio value on the cutoff date: ${portfolio_value_at_cutoff:,.2f} USD")
print(f"  (includes available cash: ${available_cash:,.2f} USD = remainder + dividends)")

# --- Full positions table: quantity, price, value, weight % and return % ---
print(f"\nPositions ({len(report_table)}) at the close of {cutoff_date} — value, weight and return:")
print(report_table[["quantity", "cutoff_price", "cutoff_value", "weight_%", "return_%"]].to_string(
    formatters={
        "quantity": "{:.2f}".format,
        "cutoff_price": "${:,.2f}".format,
        "cutoff_value": "${:,.2f}".format,
        "weight_%": "{:.2f}%".format,
        "return_%": "{:+.2f}%".format,
    }
))

# --- Dividends per position (up to the cutoff date) ---
if dividend_detail:
    dividends_df = pd.DataFrame(dividend_detail).sort_values(["ticker", "payment_date"])
    print(f"\nDividends per payment — up to the cutoff of {cutoff_date}:")
    print(dividends_df[["ticker", "payment_date", "dividend_per_share", "shares", "amount_usd"]].to_string(
        index=False,
        formatters={
            "dividend_per_share": "${:,.4f}".format,
            "shares": "{:,.2f}".format,
            "amount_usd": "${:,.2f}".format,
        }
    ))
    dividends_summary = dividends_df.groupby("ticker")["amount_usd"].sum().sort_values(ascending=False)
    dividends_total = dividends_summary.sum()
    print(f"\nTotal dividends per position — up to the cutoff of {cutoff_date}:")
    for t_, m_ in dividends_summary.items():
        print(f"  {t_:<6} ${m_:>10,.2f}   ({m_ / dividends_total * 100:>5.1f}% of total)")
    print(f"  {'TOTAL':<6} ${dividends_total:>10,.2f}")

print(f"\n--- Target amount (monthly interest of the 13% E.A. CDT) ---")
print(f"Reference capital in COP (Global66 entry rate {global66_entry_rate:,.2f}): ${reference_capital_cop:,.2f} COP")
print(f"Effective monthly rate: {cdt_monthly_rate*100:.4f}%")
print(f"Target amount to match:                ${target_amount_cop:,.2f} COP")

print(f"\n--- Cash already available (without selling anything) ---")
print(f"Dividends of the period: ${total_dividends_usd:,.2f} USD")
print(f"Total available cash (remainder + dividends): ${available_cash:,.2f} USD")

print(f"\n--- USD needed (already includes the gross-up for the {exit_fee_pct*100:.1f}% exit fee) ---")
print(f"Total USD needed to extract: ${total_usd_needed:,.2f}")

print(f"\n--- Sales needed to complete the amount ---")
if proposed_sales:
    for t, qty, usd in proposed_sales:
        print(f"  Sell {qty:.4f} shares of {t} ≈ ${usd:,.2f} USD")
else:
    print("  No need to sell anything — the available cash already covers the target amount.")

print(f"\n--- Settlement to the investor ---")
print(f"Total USD withdrawn (cash + sale): ${total_usd_extracted:,.2f}")
print(f"Gross conversion to pesos (Global66 rate {global66_exit_rate:,.2f}, {cutoff_date}): ${gross_cop:,.2f} COP")
print(f"Exit fee ({exit_fee_pct*100:.1f}%): -${exit_fee_usd * global66_exit_rate:,.2f} COP (${exit_fee_usd:,.2f} USD)")
print(f"Net delivered to the investor:          ${net_cop_delivered:,.2f} COP")
print(f"CDT target amount:                      ${target_amount_cop:,.2f} COP")
print(f"Difference (net - target):               {'+' if net_cop_delivered >= target_amount_cop else ''}{net_cop_delivered - target_amount_cop:,.2f} COP")

print(f"\n--- Hard condition check ---")
print(f"Portfolio value BEFORE the withdrawal:   ${portfolio_value_at_cutoff:,.2f} USD")
print(f"Total amount withdrawn:                  ${total_amount_withdrawn:,.2f} USD")
print(f"Portfolio value AFTER the withdrawal:    ${portfolio_value_after:,.2f} USD")
print(f"Does it stay above the actual capital disbursed (${initial_value_usd:,.2f})? {'Yes' if capital_not_affected else 'No'}")

print("\n" + "=" * 60)
if operation_is_executed:
    print("✅ RESULT: the portfolio WOULD have been able to pay the CDT equivalent this month.")
    print("   -> Add the sales from section 10 AND a CASH withdrawal to the transaction")
    print("      ledger (section 1), with the actual execution date and price.")
else:
    print("❌ RESULT: the portfolio does NOT meet the condition this month.")
    print("   No sale or withdrawal is executed. The portfolio stays the same until the next evaluation.")
print("=" * 60)

# =================================================================
# 13. WATERFALL CHART (figures of the test, truncated axis)
# =================================================================
# Path of the capital: actual capital disbursed -> entry costs -> market result
# -> value at cutoff -> withdrawal required by the CDT -> value after withdrawal.
entry_costs_usd = entry_fee_usd + gmf_paid_usd
market_result_usd = portfolio_value_at_cutoff - capital_invested_in_market
gap_vs_capital = portfolio_value_after - initial_value_usd

labels = ["Actual capital\ndisbursed", "Entry costs\n(Global66 + GMF)", "Market\nresult",
          f"Value at cutoff\n({pd.Timestamp(cutoff_date):%b %d})", "Withdrawal required\nby the CDT", "Value after\nwithdrawal"]
totals = {0: initial_value_usd, 3: portfolio_value_at_cutoff, 5: portfolio_value_after}
changes = {1: -entry_costs_usd, 2: market_result_usd, 4: -total_amount_withdrawn}

levels = [initial_value_usd, portfolio_value_at_cutoff, portfolio_value_after,
          initial_value_usd - entry_costs_usd]
axis_floor = min(levels) * 0.985
axis_ceiling = max(levels) * 1.01
pad = (axis_ceiling - axis_floor) * 0.01

fig, ax = plt.subplots(figsize=(10, 5.6))
level = initial_value_usd
for i in range(6):
    if i in totals:
        ax.bar(i, totals[i] - axis_floor, bottom=axis_floor, color="#1F3864", width=0.6)
        ax.text(i, totals[i] + pad, f"${totals[i]:,.2f}", ha="center", va="bottom",
                fontsize=9, fontweight="bold")
        level = totals[i]
    else:
        delta = changes[i]
        low, high = min(level, level + delta), max(level, level + delta)
        ax.bar(i, high - low, bottom=low, color="#1E7B34" if delta > 0 else "#B00020", width=0.6)
        ax.text(i, high + pad, f"{delta:+,.2f}", ha="center", va="bottom",
                fontsize=9, fontweight="bold")
        level += delta

ax.axhline(initial_value_usd, color="#444", ls="--", lw=1.3)
ax.text(6.15, initial_value_usd + pad, f"Capital disbursed\n${initial_value_usd:,.2f}",
        ha="right", va="bottom", fontsize=8.5, color="#444")
gap_color = "#1E7B34" if gap_vs_capital >= 0 else "#B00020"
ax.annotate("", xy=(5.4, portfolio_value_after), xytext=(5.4, initial_value_usd),
            arrowprops=dict(arrowstyle="<->", color=gap_color, lw=1.2))
ax.text(5.46, (portfolio_value_after + initial_value_usd) / 2, f"{gap_vs_capital:+,.2f}".replace("+", "+$").replace("-", "−$"),
        color=gap_color, fontsize=9, fontweight="bold", va="center")
ax.set_xticks(range(6))
ax.set_xticklabels(labels, fontsize=8.5)
ax.set_ylim(axis_floor, axis_ceiling)
ax.set_xlim(-0.5, 6.2)
ax.set_ylabel(f"USD  (truncated axis: starts at ${axis_floor:,.0f})")
ax.set_title(f"CDT Test — from disbursed capital to value after withdrawal (cutoff {cutoff_date})", fontsize=11)
ax.grid(axis="y", alpha=0.3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"${v:,.0f}"))
plt.tight_layout()
chart_file = f"cdt_waterfall_{cutoff_date}.png"
plt.savefig(chart_file, dpi=170)
print(f"\nChart saved to: {chart_file}")
plt.show()