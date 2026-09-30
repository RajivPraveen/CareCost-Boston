from decimal import Decimal

import pytest

from carecost.estimator import estimate_cost


@pytest.mark.parametrize(
    "allowed,annual,paid,rate,cap,expected",
    [
        (800, 2000, 0, 0.2, None, "800.00"),
        (2000, 2000, 1500, 0.2, None, "800.00"),
        (1000, 2000, 2000, 0.2, None, "200.00"),
        (1000, 0, 0, 0.2, None, "200.00"),
        (500, 1000, 500, 0.2, None, "500.00"),
        (1000, 1000, 1000, 0, None, "0.00"),
        (1000, 1000, 1000, 1, None, "1000.00"),
        (2000, 2000, 1500, 0.2, 600, "600.00"),
        (2000, 2000, 1500, 0.2, 0, "0.00"),
        (0, 1000, 0, 0.2, None, "0.00"),
        (10.05, 0, 0, 0.1, None, "1.01"),
    ],
)
def test_hand_calculations(allowed, annual, paid, rate, cap, expected):
    result = estimate_cost(allowed, annual, paid, rate, cap)
    assert result.patient_total == Decimal(expected)
    assert result.patient_total + result.plan_total == result.allowed_amount
    assert result.deductible_portion + result.coinsurance_portion == result.patient_total


@pytest.mark.parametrize(
    "args",
    [
        (-1, 100, 0, 0.2),
        (100, -1, 0, 0.2),
        (100, 100, 101, 0.2),
        (100, 100, 0, 20),
        (100, 100, 0, -1),
        ("NaN", 100, 0, 0.2),
        (100, 100, 0, "NaN"),
        (100, 100, 0, 0.2, -1),
    ],
)
def test_reject_invalid_plan(args):
    with pytest.raises(ValueError):
        estimate_cost(*args)
