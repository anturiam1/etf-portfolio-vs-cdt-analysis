"""
ICOLCAP TEST: COULD AN ICOLCAP PORTFOLIO PAY THE SAME AS A CDT?
===========================================================================

Same question as the CDT experiment (a CDT is a Colombian fixed-term
deposit), but with ONE single position (ICOLCAP, an ETF that tracks the MSCI
COLCAP index), bought through Trii (a Colombian online brokerage) and traded
ENTIRELY IN COLOMBIAN PESOS (no exchange rates and no Global66).

Rules of the experiment (agreed before writing the code):

1. Reference capital: $315,357,771.28 COP, the same one used as the base of
   the CDT test. It is a FIXED CEILING: the purchase fees and the 4x1000 tax
   come out of that amount (the investor cannot have more capital than in
   the ETF experiment and in the CDT).

2. Purchase (Trii): WHOLE units of ICOLCAP (no fractions).
     - fee 0.25% of the value of the shares + VAT 19% (0.2975% effective)
       (VAT = IVA, Colombia's value-added tax)
     - 4x1000 (GMF, Colombia's financial transactions tax) on shares + fee
       (VAT included)
   The maximum number of units that fit in the capital is bought; the
   leftover stays as cash in pesos.

3. Monthly target amount = reference capital x monthly rate of a CDT at
   13% E.A. (effective annual)  [ (1.13)^(1/12) - 1 ≈ 1.0237% ].

4. To cover the target, the available cash is used FIRST (leftover from the
   purchase + dividends received). If it is not enough, WHOLE units of
   ICOLCAP are sold, the minimum needed so that, after the sale fee, the net
   covers the shortfall. The surplus from unit rounding stays as cash.

5. Sale (Trii): for transactions below $5,000,000 COP the fee is a flat
   $12,500 + VAT 19% = $14,875 COP, and the 4x1000 is NOT charged. With the
   CDT target (≈ $3.2 million) that threshold is never reached; if it were,
   the script warns and calculates the sale with 0.25% + VAT.

6. HARD CONDITION: after the withdrawal, the portfolio value (remaining
   units at the closing price + cash) must be greater than or equal to the
   reference capital. If it is not met, no sale is executed that month and
   the portfolio stays the same until the next evaluation.

Documented assumptions:
  - Closing prices (opening and cutoffs) and dividends per unit are ENTERED
    BY HAND (the Colombian Stock Exchange, BVC, offers no free API).
  - No withholding tax (retención en la fuente) on dividends: the amount
    received is below the dividend-exempt amount for individuals.
  - Dividends are attributed to the PAYMENT date (issuer dates) and to the
    units held by the portfolio that day.

Project: capital markets analysis (simulated ETF portfolio)

To evaluate another cutoff (e.g. Oct 25, 2026): add the closing price to
`closing_prices`, the new dividends to `dividends` and change `cutoff_date`.
Nothing else.
"""

import math
from datetime import date

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# =================================================================
# 1. PARAMETERS (the only thing to edit)
# =================================================================
reference_capital = 315_357_771.28   # COP — fixed ceiling, same as the CDT and ETF tests

# --- Purchase at Trii ---
purchase_fee_pct = 0.0025            # 0.25% of the value of the shares
vat_pct = 0.19                       # VAT (IVA) on the fee
gmf_pct = 0.004                      # 4x1000, on shares + fee (VAT included)

# --- Sale at Trii ---
sale_flat_fee = 12_500               # COP, flat fee below the threshold
flat_fee_threshold = 5_000_000       # COP, above it 0.25% + VAT applies
sale_fee_pct = 0.0025                # only if the sale exceeds the threshold
# A sale below the threshold pays no 4x1000. Above the threshold it is not
# known whether it does; the script only warns (it should not happen with the
# CDT target).

# --- Reference CDT ---
cdt_annual_rate = 0.13
cdt_monthly_rate = (1 + cdt_annual_rate) ** (1 / 12) - 1   # ≈ 1.0237%

# --- Dates and prices entered by hand (COP per unit) ---
opening_date = date(2026, 8, 25)
opening_price = 24_721
cutoff_date = date(2026, 9, 25)
closing_prices = {
    date(2026, 9, 25): 25_846,
}

# --- Dividends per unit, by PAYMENT date (issuer dates) ---
dividends = [
    (date(2026, 9, 4), 4.92),      # record date Aug 31, 2026
    (date(2026, 10, 6), 154.84),   # record date Sep 30, 2026 (falls after the first cutoff)
]

# =================================================================
# 2. HELPER FUNCTIONS
# =================================================================
def cop(x, decimals=2):
    return f"${x:,.{decimals}f}"


purchase_fee_factor = purchase_fee_pct * (1 + vat_pct)               # 0.2975% effective
purchase_cost_factor = (1 + purchase_fee_factor) * (1 + gmf_pct)     # total cost per peso of shares


def purchase_cost(units, price):
    value = units * price
    fee = value * purchase_fee_factor                                # fee + VAT
    gmf = (value + fee) * gmf_pct
    return value, fee, gmf, value + fee + gmf


def sale_fee(gross):
    """Sale fee with VAT included; the 4x1000 does not apply below the threshold."""
    if gross < flat_fee_threshold:
        return sale_flat_fee * (1 + vat_pct)
    return gross * sale_fee_pct * (1 + vat_pct)


if cutoff_date not in closing_prices:
    raise ValueError(f"The closing price of {cutoff_date} is missing in `closing_prices`.")
cutoff_price = closing_prices[cutoff_date]

# =================================================================
# 3. OPENING: WHOLE UNITS THAT FIT IN THE CAPITAL
# =================================================================
units = math.floor(reference_capital / (opening_price * purchase_cost_factor))
# Defensive check against floating-point errors
while purchase_cost(units, opening_price)[3] > reference_capital:
    units -= 1
while purchase_cost(units + 1, opening_price)[3] <= reference_capital:
    units += 1

purchase_value, purchase_fee, purchase_gmf, total_debited = purchase_cost(units, opening_price)
leftover_cash = reference_capital - total_debited
entry_costs = purchase_fee + purchase_gmf
assert total_debited <= reference_capital and leftover_cash >= 0

print("=" * 72)
print("TEST: WOULD ICOLCAP HAVE PAID THE SAME AS A CDT?")
print(f"Period evaluated: {opening_date} to {cutoff_date}")
print("=" * 72)

print("\n--- Opening (purchase at Trii, whole units) ---")
print(f"Reference capital (ceiling):              {cop(reference_capital)} COP")
print(f"Purchase price {opening_date}:             {cop(opening_price, 0)} COP")
print(f"Units bought:                             {units:,}")
print(f"Value of the shares:                      {cop(purchase_value)} COP")
print(f"Trii fee (0.25% + VAT 19%):               {cop(purchase_fee)} COP")
print(f"4x1000 tax (GMF 0.4%):                    {cop(purchase_gmf)} COP")
print(f"Total debited:                            {cop(total_debited)} COP")
print(f"Leftover cash:                            {cop(leftover_cash)} COP")
print(f"Entry costs:                              {cop(entry_costs)} COP "
      f"({entry_costs / reference_capital * 100:.2f}% of the capital)")

# =================================================================
# 4. DIVIDENDS OF THE PERIOD AND AVAILABLE CASH
# =================================================================
dividend_detail = []
for payment_date, per_unit in sorted(dividends):
    if opening_date < payment_date <= cutoff_date:
        dividend_detail.append((payment_date, per_unit, units, units * per_unit))

total_dividends = sum(d[3] for d in dividend_detail)
cash = leftover_cash + total_dividends

print("\n--- Dividends of the period ---")
if dividend_detail:
    for payment_date, per_unit, n, amount in dividend_detail:
        print(f"  Payment {payment_date}: {cop(per_unit)} per unit x {n:,} units = {cop(amount)} COP")
else:
    print("  No dividends paid in the period.")
later_payments = [(d, v) for d, v in sorted(dividends) if d > cutoff_date]
if later_payments:
    print("  (Payments after the cutoff, for the next evaluation: "
          + ", ".join(f"{d}: {cop(v)}/unit" for d, v in later_payments) + ")")
print(f"Total dividends of the period:            {cop(total_dividends)} COP")
print(f"Available cash (leftover + dividends):    {cop(cash)} COP")

# =================================================================
# 5. STATE AT THE CUTOFF
# =================================================================
units_value = units * cutoff_price
total_value = units_value + cash
net_return = total_value / reference_capital - 1
return_before_costs = (units_value + total_dividends) / purchase_value - 1
market_result = total_value - (reference_capital - entry_costs)  # units x price change + dividends

print(f"\n--- State at the cutoff ({cutoff_date}) ---")
print(f"Closing price:                            {cop(cutoff_price, 0)} COP "
      f"({(cutoff_price / opening_price - 1) * 100:+.2f}% vs purchase)")
print(f"Value of the units:                       {cop(units_value)} COP")
print(f"Cash:                                     {cop(cash)} COP")
print(f"Total portfolio value:                    {cop(total_value)} COP")
print(f"Net return on the capital:                {net_return * 100:+.2f}%")
print(f"Return before entry costs:                {return_before_costs * 100:+.2f}%  (context only)")

# =================================================================
# 6. CDT TARGET AMOUNT
# =================================================================
target = reference_capital * cdt_monthly_rate

print("\n--- Target amount (monthly interest of the 13% E.A. CDT) ---")
print(f"Effective monthly rate:                   {cdt_monthly_rate * 100:.4f}%")
print(f"Target amount to match:                   {cop(target)} COP")

# =================================================================
# 7. SETTLEMENT: CASH FIRST, THEN WHOLE UNITS
# =================================================================
cash_used = min(cash, target)
shortfall = target - cash_used

units_to_sell, gross_sale, sale_fee_cop, net_sale = 0, 0.0, 0.0, 0.0
if shortfall > 0:
    units_to_sell = None
    for n in range(1, units + 1):
        g = n * cutoff_price
        f = sale_fee(g)
        if g - f >= shortfall:
            units_to_sell, gross_sale, sale_fee_cop, net_sale = n, g, f, g - f
            break
    if units_to_sell is None:
        print("\n⚠️  Even selling all the units the target is not reached.")
        raise SystemExit(1)
    if gross_sale >= flat_fee_threshold:
        print(f"\n⚠️  The sale (${gross_sale:,.0f}) exceeds the threshold of ${flat_fee_threshold:,.0f}: "
              "0.25% + VAT was applied and the 4x1000 was NOT calculated. Confirm the actual fee.")

final_cash = cash + net_sale - target
delivered = target                              # the surplus from rounding stays in the portfolio as cash

print("\n--- Cash already available (without selling anything) ---")
print(f"Cash used for the target:                 {cop(cash_used)} COP")
print(f"Shortfall to cover with a sale:           {cop(shortfall)} COP")

print("\n--- ICOLCAP sale (whole units) ---")
if units_to_sell:
    print(f"Units to sell:                            {units_to_sell:,} at {cop(cutoff_price, 0)} COP")
    print(f"Gross sale:                               {cop(gross_sale)} COP")
    print(f"Sale fee (${sale_flat_fee:,.0f} + VAT 19%):          -{cop(sale_fee_cop)} COP")
    print(f"Net from the sale:                        {cop(net_sale)} COP")
else:
    print("No sale needed: the cash covers the target.")

print("\n--- Settlement to the investor ---")
print(f"Delivered to the investor:                {cop(delivered)} COP")
print(f"CDT target amount:                        {cop(target)} COP")
print(f"Difference (delivered - target):          {cop(delivered - target)}")
print(f"Cash left in the portfolio:               {cop(final_cash)} COP")

# =================================================================
# 8. HARD CONDITION
# =================================================================
remaining_units = units - units_to_sell
value_after = remaining_units * cutoff_price + final_cash
margin = value_after - reference_capital
passes = value_after >= reference_capital
total_withdrawal = total_value - value_after   # target + sale fee

print("\n--- Hard condition check ---")
print(f"Portfolio value BEFORE the withdrawal:    {cop(total_value)} COP")
print(f"Total withdrawal from the portfolio:      {cop(total_withdrawal)} COP (target + sale fee)")
print(f"Remaining units:                          {remaining_units:,}")
print(f"Portfolio value AFTER the withdrawal:     {cop(value_after)} COP")
print(f"Reference capital (threshold):            {cop(reference_capital)} COP")
print(f"Margin versus the threshold:              {cop(margin)} COP ({margin / reference_capital * 100:+.2f}%)")
print(f"Does it stay above the capital?           {'Yes' if passes else 'No'}")

print("\n" + "=" * 72)
if passes:
    print("✅ RESULT: the portfolio MEETS the condition this month.")
    print("   The sale and the withdrawal of the CDT-equivalent amount would be executed.")
else:
    print("❌ RESULT: the portfolio does NOT meet the condition this month.")
    print("   No sale or withdrawal is executed. The portfolio stays the same")
    print("   until the next evaluation.")
print("=" * 72)

# =================================================================
# 9. WATERFALL CHART (figures of the test, truncated axis)
# =================================================================
labels = ["Reference\ncapital", "Entry costs\n(fee + 4x1000)", "Market result\n+ dividends",
          f"Value at cutoff\n({cutoff_date:%b %d})", "Withdrawal required\n(target + fee)", "Value after\nwithdrawal"]
totals = {0: reference_capital, 3: total_value, 5: value_after}
changes = {1: -entry_costs, 2: market_result, 4: -total_withdrawal}

levels = [reference_capital, total_value, value_after, reference_capital - entry_costs]
axis_floor = min(levels) * 0.985
axis_ceiling = max(levels) * 1.01
fig, ax = plt.subplots(figsize=(10, 5.6))
level = reference_capital
for i in range(6):
    if i in totals:
        ax.bar(i, totals[i] - axis_floor, bottom=axis_floor, color="#1F3864", width=0.6)
        ax.text(i, totals[i] + (axis_ceiling - axis_floor) * 0.01, f"${totals[i] / 1e6:,.2f} M", ha="center", va="bottom",
                fontsize=9, fontweight="bold")
        level = totals[i]
    else:
        d = changes[i]
        lo, hi = min(level, level + d), max(level, level + d)
        ax.bar(i, hi - lo, bottom=lo, color="#1E7B34" if d > 0 else "#B00020", width=0.6)
        ax.text(i, hi + (axis_ceiling - axis_floor) * 0.01, f"{d / 1e6:+,.2f} M", ha="center", va="bottom",
                fontsize=9, fontweight="bold")
        level += d

ax.axhline(reference_capital, color="#444", ls="--", lw=1.3)
ax.text(4, reference_capital - (axis_ceiling - axis_floor) * 0.015,
        f"Reference capital: ${reference_capital / 1e6:,.2f} M", ha="center", va="top", fontsize=8.5, color="#444")
ax.set_xticks(range(6))
ax.set_xticklabels(labels, fontsize=8.5)
ax.set_ylim(axis_floor, axis_ceiling)
ax.set_xlim(-0.5, 5.5)
ax.set_ylabel(f"Millions of COP  (truncated axis: starts at ${axis_floor / 1e6:,.0f} M)")
ax.set_title(f"ICOLCAP Test — from reference capital to value after withdrawal (cutoff {cutoff_date})", fontsize=11)
ax.grid(axis="y", alpha=0.3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"${v / 1e6:,.0f}"))
plt.tight_layout()
chart_file = f"icolcap_waterfall_{cutoff_date}.png"
plt.savefig(chart_file, dpi=170)
print(f"\nChart saved to: {chart_file}")
plt.show()