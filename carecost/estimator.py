from dataclasses import dataclass
from decimal import Decimal

from carecost.models import money


@dataclass(frozen=True)
class Estimate:
    allowed_amount: Decimal
    deductible_portion: Decimal
    coinsurance_portion: Decimal
    patient_total: Decimal
    plan_total: Decimal
    remaining_deductible_after: Decimal
    capped_by_oop_max: bool


def estimate_cost(allowed_amount, deductible, deductible_paid, coinsurance, oop_remaining=None) -> Estimate:
    """One covered, in-network service; coinsurance is a fraction in [0, 1].

    Copays, family accumulators, benefit exclusions and balance billing are outside this model.
    An optional remaining out-of-pocket maximum caps the total patient share.
    """
    allowed, annual, paid = map(money, (allowed_amount, deductible, deductible_paid))
    rate = Decimal(str(coinsurance))
    if min(allowed, annual, paid) < 0 or paid > annual:
        raise ValueError("Use nonnegative amounts; deductible paid cannot exceed the annual deductible.")
    if not rate.is_finite() or not 0 <= rate <= 1:
        raise ValueError("Coinsurance must be between 0 and 100 percent.")
    remaining = annual - paid
    ded = min(allowed, remaining)
    coins = money((allowed - ded) * rate)
    total = ded + coins
    capped = False
    if oop_remaining is not None:
        cap = money(oop_remaining)
        if cap < 0:
            raise ValueError("Remaining out-of-pocket maximum cannot be negative.")
        if cap < total:
            capped = True
            total = cap
            ded = min(ded, cap)
            coins = total - ded
    return Estimate(allowed, ded, coins, total, allowed - total, remaining - ded, capped)
