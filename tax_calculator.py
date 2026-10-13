from decimal import Decimal, ROUND_HALF_UP


ZERO = Decimal("0")
FOUR_PERCENT = Decimal("0.04")

STANDARD_DEDUCTION = Decimal("75000")
REBATE_LIMIT = Decimal("1200000")
MAX_REBATE = Decimal("60000")


def money(value):
    """Round an amount to two decimal places."""
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )


def calculate_slab_tax(taxable_income):
    """
    Calculate tax using the new-regime slabs applicable
    for Tax Year 2026-27 for an individual with normal income.
    """

    income = taxable_income
    tax = ZERO

    slabs = [
        (Decimal("400000"), Decimal("0.00")),
        (Decimal("800000"), Decimal("0.05")),
        (Decimal("1200000"), Decimal("0.10")),
        (Decimal("1600000"), Decimal("0.15")),
        (Decimal("2000000"), Decimal("0.20")),
        (Decimal("2400000"), Decimal("0.25")),
        (None, Decimal("0.30")),
    ]

    lower_limit = ZERO

    for upper_limit, rate in slabs:

        if upper_limit is None:
            taxable_in_slab = max(ZERO, income - lower_limit)
        else:
            taxable_in_slab = max(
                ZERO,
                min(income, upper_limit) - lower_limit
            )

        tax += taxable_in_slab * rate

        if upper_limit is not None and income <= upper_limit:
            break

        if upper_limit is not None:
            lower_limit = upper_limit

    return money(tax)


def calculate_new_regime_tax(
    salary_income,
    house_property_income,
    other_income,
    eligible_deductions,
    tds_amount,
):
    """
    Educational calculator for ordinary income under the
    new tax regime for Tax Year 2026-27.

    Limitations:
    - Assumes an eligible individual taxpayer.
    - Does not handle special-rate income or surcharge.
    - Only applies the salary standard deduction.
    - Other deductions are not automatically allowed under
      the new regime.
    """

    salary = money(salary_income)
    house = money(house_property_income)
    other = money(other_income)
    deductions_entered = money(eligible_deductions)
    tds = money(tds_amount)

    amounts = [salary, house, other, deductions_entered, tds]

    if any(amount < ZERO for amount in amounts):
        raise ValueError("Amounts cannot be negative.")

    # Gross total income
    gross_income = money(salary + house + other)

    # Standard deduction is limited to salary income.
    standard_deduction = min(salary, STANDARD_DEDUCTION)

    # The new regime generally restricts deductions.
    # The amount entered as other deductions is not automatically
    # subtracted from taxable income.
    taxable_income = money(
        max(ZERO, gross_income - standard_deduction)
    )

    # Tax before rebate
    tax_before_rebate = calculate_slab_tax(taxable_income)

    # Section 87A rebate for eligible resident individuals.
    if taxable_income <= REBATE_LIMIT:
        rebate = min(tax_before_rebate, MAX_REBATE)
    else:
        rebate = ZERO

        # Marginal relief near the ₹12 lakh threshold:
        # tax after relief cannot exceed income above ₹12 lakh.
        excess_income = taxable_income - REBATE_LIMIT

        if tax_before_rebate > excess_income:
            rebate = tax_before_rebate - excess_income

    tax_after_rebate = money(
        max(ZERO, tax_before_rebate - rebate)
    )

    # Health and education cess
    cess = money(tax_after_rebate * FOUR_PERCENT)

    total_tax = money(tax_after_rebate + cess)

    # TDS is tax already deducted, not a deduction from income.
    tax_payable = money(max(ZERO, total_tax - tds))
    refund_estimate = money(max(ZERO, tds - total_tax))

    return {
        "gross_total_income": gross_income,
        "standard_deduction": standard_deduction,
        "eligible_deductions_entered": deductions_entered,
        "taxable_income": taxable_income,
        "tax_before_rebate": tax_before_rebate,
        "rebate": money(rebate),
        "income_tax": tax_after_rebate,
        "cess": cess,
        "total_tax_liability": total_tax,
        "tds_amount": tds,
        "tax_payable": tax_payable,
        "refund_estimate": refund_estimate,
        "financial_year": "2026-2027",
    }