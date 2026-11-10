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
     - 4x1000 (GMF, Colombia's financial transactions tax, a government
       tax and not a Trii fee) on shares + fee (VAT included)
   The maximum number of units that fit in the capital is bought; the
   leftover stays as cash in pesos.

3. Monthly target amount = reference capital x monthly rate of a CDT at
   13% E.A. (effective annual)  [ (1.13)^(1/12) - 1 ≈ 1.0237% ].

4. To cover the target, the available cash is used FIRST (leftover from the
   purchase + dividends received). If it is not enough, WHOLE units of
   ICOLCAP are sold, the minimum needed so that, after the sale fee, the net
   covers the shortfall. The surplus from unit rounding stays as cash.

5. Sale (Trii): for transactions below $5,000,000 COP the fee is a flat
   $12,500 + VAT 19% = $14,875 COP, and the 4x1000 is NOT charged. For
   sales of $5,000,000 COP or more, whether the 4x1000 is charged is not
   confirmed. With the CDT target (≈ $3.2 million) that threshold is never
   reached; if it were, the script warns and calculates the sale with
   0.25% + VAT.

6. HARD CONDITION: after the withdrawal, the portfolio value (remaining
   units at the closing price + cash) must be greater than or equal to the
   reference capital. If it is not met, no sale is executed that month and
   the portfolio stays the same until the next evaluation.

7. CHAINING OF THE CUTOFFS: each cutoff starts from the state in which the
   previous one left the portfolio. If the condition was met at a cutoff,
   the sale and the withdrawal WERE executed: the units sold are no longer
   in the portfolio and the remaining cash moves on to the next cutoff. If
   it was not met, there was no sale or withdrawal and the cash (dividends
   included) accumulates. Each cutoff is measured against ONE month of
   interest (the target does not accumulate). The dividends of each cutoff
   are only those paid AFTER the previous cutoff and up to the evaluated
   cutoff, on the units held that day.

Documented assumptions:
  - Closing prices (opening and cutoffs) and dividends per unit are ENTERED
    BY HAND (the Colombian Stock Exchange, BVC, offers no free API).
  - No withholding tax (retención en la fuente) on dividends: the amount
    received is below the dividend-exempt amount for individuals.
  - Dividends are attributed to the PAYMENT date (issuer dates) and to the
    units held by the portfolio that day.

Project: capital markets analysis (simulated ETF portfolio)

To evaluate another cutoff (e.g. Nov 25, 2026): add its closing price to
`closing_prices`, the new dividends to `dividends` and change `cutoff_date`.
The script walks through all the cutoffs in `closing_prices` in order, up to
`cutoff_date`, applying the sales of the cutoffs that met the condition.
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
gmf_pct = 0.004                      # 4x1000 (government tax), on shares + fee (VAT included)

# --- Sale at Trii ---
sale_flat_fee = 12_500               # COP, flat fee below the threshold
flat_fee_threshold = 5_000_000       # COP, above it 0.25% + VAT applies
sale_fee_pct = 0.0025                # only if the sale exceeds the threshold
# A sale below the threshold pays no 4x1000. From the threshold up it is not
# confirmed whether it does; the script only warns (it should not happen with
# the CDT target).

# --- Reference CDT ---
cdt_annual_rate = 0.13
cdt_monthly_rate = (1 + cdt_annual_rate) ** (1 / 12) - 1   # ≈ 1.0237%

# --- Dates and prices entered by hand (COP per unit) ---
opening_date = date(2026, 8, 25)
opening_price = 24_721
cutoff_date = date(2026, 10, 26)     # cutoff to evaluate
closing_prices = {                   # one price per cutoff, in chronological order
    date(2026, 9, 25): 25_846,
    date(2026, 10, 26): 24_670,
}

# --- Dividends per unit, by PAYMENT date (issuer dates) ---
dividends = [
    (date(2026, 9, 4), 4.92),      # record date Aug 31, 2026
    (date(2026, 10, 6), 154.84),   # record date Sep 30, 2026
]


# =================================================================
# 2. HELPER FUNCTIONS
# =================================================================
def cop(x, decimals=2):
    return f"-${abs(x):,.{decimals}f}" if x < 0 else f"${x:,.{decimals}f}"


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


def evaluate_cutoff(cut_date, price, units, starting_cash, since_date):
    """Evaluates ONE cutoff from the current state (units and cash).

    Returns a dictionary with all the figures of the cutoff; it does not modify the state.
    """
    payments = [(d, v, units, units * v) for d, v in sorted(dividends) if since_date < d <= cut_date]
    total_div = sum(p[3] for p in payments)
    cash = starting_cash + total_div
    units_value = units * price
    total_value = units_value + cash
    target = reference_capital * cdt_monthly_rate

    cash_used = min(cash, target)
    shortfall = target - cash_used
    units_to_sell, gross, fee, net = 0, 0.0, 0.0, 0.0
    if shortfall > 0:
        units_to_sell = None
        for n in range(1, units + 1):
            g = n * price
            f = sale_fee(g)
            if g - f >= shortfall:
                units_to_sell, gross, fee, net = n, g, f, g - f
                break
    if units_to_sell is None:
        return {"no_units": True, "cut_date": cut_date}

    final_cash = cash + net - target
    value_after = (units - units_to_sell) * price + final_cash
    return {
        "no_units": False, "cut_date": cut_date, "price": price, "units": units,
        "payments": payments, "total_div": total_div, "cash": cash, "units_value": units_value,
        "total_value": total_value, "target": target, "cash_used": cash_used,
        "shortfall": shortfall, "units_to_sell": units_to_sell, "gross": gross, "fee": fee, "net": net,
        "final_cash": final_cash, "value_after": value_after,
        "total_withdrawal": total_value - value_after,          # target + sale fee
        "passes": value_after >= reference_capital,
    }


if cutoff_date not in closing_prices:
    raise ValueError(f"The closing price of {cutoff_date} is missing in `closing_prices`.")
cutoffs = sorted(d for d in closing_prices if d <= cutoff_date)

# =================================================================
# 3. OPENING: WHOLE UNITS THAT FIT IN THE CAPITAL
# =================================================================
units_bought = math.floor(reference_capital / (opening_price * purchase_cost_factor))
# Defensive check against floating-point errors
while purchase_cost(units_bought, opening_price)[3] > reference_capital:
    units_bought -= 1
while purchase_cost(units_bought + 1, opening_price)[3] <= reference_capital:
    units_bought += 1

purchase_value, purchase_fee, purchase_gmf, total_debited = purchase_cost(units_bought, opening_price)
leftover_cash = reference_capital - total_debited
entry_costs = purchase_fee + purchase_gmf
assert total_debited <= reference_capital and leftover_cash >= 0

# =================================================================
# 4. WALK THROUGH THE CUTOFFS (each one starts from the state of the previous one)
# =================================================================
current_units = units_bought
current_cash = leftover_cash
since_date = opening_date
previous_withdrawals = 0.0   # total already withdrawn from the portfolio at earlier cutoffs
previous_sales = 0.0         # gross ICOLCAP sales at earlier cutoffs
previous_dividends = 0.0     # dividends received at earlier cutoffs
history = []

for d in cutoffs:
    previous = {"units": current_units, "cash": current_cash, "since_date": since_date,
                "withdrawals": previous_withdrawals, "sales": previous_sales, "div": previous_dividends}
    r = evaluate_cutoff(d, closing_prices[d], current_units, current_cash, since_date)
    if r["no_units"]:
        print(f"\n⚠️  Even selling all the units the target is not reached (cutoff {d}).")
        raise SystemExit(1)
    if d != cutoff_date:
        history.append(r)
    # Move on to the next cutoff: if it passed, the sale and the withdrawal WERE executed
    if r["passes"]:
        current_units -= r["units_to_sell"]
        current_cash = r["final_cash"]
        previous_withdrawals += r["total_withdrawal"]
        previous_sales += r["gross"]
    else:
        current_cash = r["cash"]             # no sale or withdrawal; the dividends accumulate
    previous_dividends += r["total_div"]
    since_date = d

# r and previous now correspond to the evaluated cutoff (cutoff_date)
units = r["units"]
cutoff_price = r["price"]
total_dividends = r["total_div"]
cash = r["cash"]
units_value = r["units_value"]
total_value = r["total_value"]
target = r["target"]
previous_withdrawals = previous["withdrawals"]
previous_sales = previous["sales"]
accumulated_dividends = previous["div"] + total_dividends

print("=" * 72)
print("TEST: WOULD ICOLCAP HAVE PAID THE SAME AS A CDT?")
print(f"Period evaluated: {opening_date} to {cutoff_date}")
print("=" * 72)

print("\n--- Opening (purchase at Trii, whole units) ---")
print(f"Reference capital (ceiling):              {cop(reference_capital)} COP")
print(f"Purchase price {opening_date}:             {cop(opening_price, 0)} COP")
print(f"Units bought:                             {units_bought:,}")
print(f"Value of the shares:                      {cop(purchase_value)} COP")
print(f"Trii fee (0.25% + VAT 19%):               {cop(purchase_fee)} COP")
print(f"4x1000 tax (GMF 0.4%):                    {cop(purchase_gmf)} COP")
print(f"Total debited:                            {cop(total_debited)} COP")
print(f"Leftover cash:                            {cop(leftover_cash)} COP")
print(f"Entry costs:                              {cop(entry_costs)} COP "
      f"({entry_costs / reference_capital * 100:.2f}% of the capital)")

if history:
    print("\n--- Previous cutoffs (already evaluated; their result carries over) ---")
    for h in history:
        print(f"  Cutoff {h['cut_date']}: price {cop(h['price'], 0)}, value before the withdrawal {cop(h['total_value'])} COP")
        if h["passes"]:
            print(f"    MET: sold {h['units_to_sell']:,} units, delivered {cop(h['target'])} COP; "
                  f"{h['units'] - h['units_to_sell']:,} units and {cop(h['final_cash'])} COP in cash remained")
        else:
            print("    NOT MET: no sale or withdrawal; the cash accumulated")
    print(f"\n--- Position held at the start of the period ({previous['since_date']} to {cutoff_date}) ---")
    print(f"Units held:                               {previous['units']:,}")
    print(f"Cash held:                                {cop(previous['cash'])} COP")

# =================================================================
# 5. DIVIDENDS OF THE PERIOD AND AVAILABLE CASH
# =================================================================
print("\n--- Dividends of the period ---")
if r["payments"]:
    for payment_date, per_unit, n, amount in r["payments"]:
        print(f"  Payment {payment_date}: {cop(per_unit)} per unit x {n:,} units = {cop(amount)} COP")
else:
    print("  No dividends paid in the period.")
later_payments = [(d, v) for d, v in sorted(dividends) if d > cutoff_date]
if later_payments:
    print("  (Payments after the cutoff, for the next evaluation: "
          + ", ".join(f"{d}: {cop(v)}/unit" for d, v in later_payments) + ")")
print(f"Total dividends of the period:            {cop(total_dividends)} COP")
print(f"Available cash (cash held + dividends):   {cop(cash)} COP")

# =================================================================
# 6. STATE AT THE CUTOFF
# =================================================================
net_return = total_value / reference_capital - 1
net_return_with_withdrawals = (total_value + previous_withdrawals) / reference_capital - 1
return_before_costs = (units_value + previous_sales + accumulated_dividends) / purchase_value - 1
# units x price change + dividends (+ previous withdrawals, which already left the portfolio)
market_result = total_value - (reference_capital - entry_costs) + previous_withdrawals

print(f"\n--- State at the cutoff ({cutoff_date}) ---")
print(f"Closing price:                            {cop(cutoff_price, 0)} COP "
      f"({(cutoff_price / opening_price - 1) * 100:+.2f}% vs purchase)")
print(f"Units held:                               {units:,}")
print(f"Value of the units:                       {cop(units_value)} COP")
print(f"Cash:                                     {cop(cash)} COP")
print(f"Total portfolio value:                    {cop(total_value)} COP")
print(f"Net return on the capital:                {net_return * 100:+.2f}%")
if previous_withdrawals > 0:
    print(f"Withdrawals from previous cutoffs:        {cop(previous_withdrawals)} COP")
    print(f"Net return including those withdrawals:   {net_return_with_withdrawals * 100:+.2f}%  (context)")
print(f"Return before entry costs:                {return_before_costs * 100:+.2f}%  (context only)")

# =================================================================
# 7. CDT TARGET AMOUNT
# =================================================================
print("\n--- Target amount (monthly interest of the 13% E.A. CDT) ---")
print(f"Effective monthly rate:                   {cdt_monthly_rate * 100:.4f}%")
print(f"Target amount to match:                   {cop(target)} COP")

# =================================================================
# 8. SETTLEMENT: CASH FIRST, THEN WHOLE UNITS
# =================================================================
units_to_sell, gross_sale, sale_fee_cop, net_sale = r["units_to_sell"], r["gross"], r["fee"], r["net"]
if gross_sale >= flat_fee_threshold:
    print(f"\n⚠️  The sale (${gross_sale:,.0f}) reaches the threshold of ${flat_fee_threshold:,.0f}: "
          "0.25% + VAT was applied and the 4x1000 was NOT calculated. Confirm the actual fee.")
final_cash = r["final_cash"]
delivered = target                              # the surplus from rounding stays in the portfolio as cash

print("\n--- Cash already available (without selling anything) ---")
print(f"Cash used for the target:                 {cop(r['cash_used'])} COP")
print(f"Shortfall to cover with a sale:           {cop(r['shortfall'])} COP")

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
# 9. HARD CONDITION
# =================================================================
remaining_units = units - units_to_sell
value_after = r["value_after"]
margin = value_after - reference_capital
passes = r["passes"]
total_withdrawal = r["total_withdrawal"]   # target + sale fee

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
# 10. WATERFALL CHART (figures of the test, truncated axis)
# =================================================================
# Each step: (label, type, value). "total" = bar from the base; "change" = floating variation.
steps = [
    ("Reference\ncapital", "total", reference_capital),
    ("Entry costs\n(fee + 4x1000)", "change", -entry_costs),
    ("Market result\n+ dividends", "change", market_result),
]
if previous_withdrawals > 0:
    steps.append(("Withdrawals from\nprevious cutoffs", "change", -previous_withdrawals))
steps += [
    (f"Value at cutoff\n({cutoff_date:%b %d})", "total", total_value),
    ("Withdrawal required\n(target + fee)", "change", -total_withdrawal),
    ("Value after\nwithdrawal", "total", value_after),
]

# First pass: levels reached, to set the truncated axis
levels, level = [], reference_capital
for _, kind, v in steps:
    level = v if kind == "total" else level + v
    levels.append(level)
axis_floor = min(levels + [reference_capital]) * 0.985
axis_ceiling = max(levels + [reference_capital]) * 1.01

n_steps = len(steps)
fig, ax = plt.subplots(figsize=(10 if n_steps <= 6 else 11.5, 5.6))   # wider with 7 bars (long labels)
level = reference_capital
for i, (_, kind, v) in enumerate(steps):
    if kind == "total":
        ax.bar(i, v - axis_floor, bottom=axis_floor, color="#1F3864", width=0.6)
        ax.text(i, v + (axis_ceiling - axis_floor) * 0.01, f"${v / 1e6:,.2f} M", ha="center", va="bottom",
                fontsize=9, fontweight="bold")
        level = v
    else:
        lo, hi = min(level, level + v), max(level, level + v)
        ax.bar(i, hi - lo, bottom=lo, color="#1E7B34" if v > 0 else "#B00020", width=0.6)
        ax.text(i, hi + (axis_ceiling - axis_floor) * 0.01, f"{v / 1e6:+,.2f} M", ha="center", va="bottom",
                fontsize=9, fontweight="bold")
        level += v

ax.axhline(reference_capital, color="#444", ls="--", lw=1.3)
ax.text(n_steps - 2, reference_capital - (axis_ceiling - axis_floor) * 0.015,
        f"Reference capital: ${reference_capital / 1e6:,.2f} M", ha="center", va="top", fontsize=8.5, color="#444")
ax.set_xticks(range(n_steps))
ax.set_xticklabels([s[0] for s in steps], fontsize=8.5 if n_steps <= 6 else 8)
ax.set_ylim(axis_floor, axis_ceiling)
ax.set_xlim(-0.5, n_steps - 0.5)
ax.set_ylabel(f"Millions of COP  (truncated axis: starts at ${axis_floor / 1e6:,.0f} M)")
ax.set_title(f"ICOLCAP Test — from reference capital to value after withdrawal (cutoff {cutoff_date})", fontsize=11)
ax.grid(axis="y", alpha=0.3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, p: f"${v / 1e6:,.0f}"))
plt.tight_layout()
chart_file = f"icolcap_waterfall_{cutoff_date}.png"
plt.savefig(chart_file, dpi=170)
print(f"\nChart saved to: {chart_file}")
plt.show()