import pytest

from services.pricing import PricingPolicyError, calculate_proposed_price


def _policy(**overrides):
    policy = {
        "version": "smartstore-pricing:v1",
        "shippingCost": {"type": "fixed", "amount": 3000},
        "marketplaceFee": {"type": "percent_of_sale_price", "rate": 5.0},
        "advertisingCost": {"type": "percent_of_sale_price", "rate": 3.0},
        "otherCost": {"type": "fixed", "amount": 500},
        "targetMargin": {"type": "percent_of_sale_price", "rate": 25.0},
        "rounding": {"unit": 100, "mode": "ceil"},
    }
    policy.update(overrides)
    return policy


def test_calculates_sale_price_and_achieved_margin_from_account_policy():
    result = calculate_proposed_price(cost_price=8000, policy=_policy())

    assert result == {
        "policyVersion": "smartstore-pricing:v1",
        "costPrice": 8000,
        "proposedSalePrice": 17200,
        "shippingCost": 3000,
        "marketplaceFee": 860,
        "advertisingCost": 516,
        "otherCost": 500,
        "expectedProfit": 4324,
        "expectedMarginRate": 25.14,
    }


def test_supports_sale_price_percentage_other_cost():
    result = calculate_proposed_price(
        cost_price=8000,
        policy=_policy(
            shippingCost={"type": "fixed", "amount": 0},
            advertisingCost={"type": "percent_of_sale_price", "rate": 0},
            otherCost={"type": "percent_of_sale_price", "rate": 5},
            targetMargin={"type": "percent_of_sale_price", "rate": 20},
        ),
    )

    assert result["proposedSalePrice"] == 11500
    assert result["marketplaceFee"] == 575
    assert result["otherCost"] == 575
    assert result["expectedProfit"] == 2350
    assert result["expectedMarginRate"] == 20.43


@pytest.mark.parametrize(
    ("cost_price", "policy", "message"),
    [
        (8000, None, "pricing policy is required"),
        (None, _policy(), "cost price is required"),
        (0, _policy(), "cost price must be positive"),
        (
            8000,
            _policy(
                marketplaceFee={"type": "percent_of_sale_price", "rate": 60},
                advertisingCost={"type": "percent_of_sale_price", "rate": 20},
                targetMargin={"type": "percent_of_sale_price", "rate": 30},
            ),
            "percentage rates must total less than 100",
        ),
        (
            8000,
            _policy(rounding={"unit": 100, "mode": "floor"}),
            "rounding mode",
        ),
        (
            8000,
            _policy(shippingCost={"type": "fixed", "amount": -1}),
            "shippingCost",
        ),
    ],
)
def test_invalid_pricing_policy_blocks_draft_generation(cost_price, policy, message):
    with pytest.raises(PricingPolicyError, match=message):
        calculate_proposed_price(cost_price=cost_price, policy=policy)


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (
            {key: value for key, value in _policy().items() if key != "marketplaceFee"},
            "marketplaceFee is required",
        ),
        (
            {key: value for key, value in _policy().items() if key != "rounding"},
            "rounding is required",
        ),
        (
            _policy(marketplaceFee={"type": "percent_of_sale_price"}),
            "marketplaceFee rate is required",
        ),
        (
            _policy(shippingCost={"type": "fixed"}),
            "shippingCost amount is required",
        ),
        (
            _policy(marketplaceFee=[]),
            "marketplaceFee must be an object",
        ),
        (
            _policy(rounding={"mode": "ceil"}),
            "rounding unit is required",
        ),
    ],
)
def test_incomplete_or_malformed_policy_does_not_infer_a_sale_price(policy, message):
    with pytest.raises(PricingPolicyError, match=message):
        calculate_proposed_price(cost_price=8000, policy=policy)


def test_rounding_of_component_fees_cannot_undercut_target_margin():
    result = calculate_proposed_price(
        cost_price=6699,
        policy=_policy(
            shippingCost={"type": "fixed", "amount": 0},
            marketplaceFee={"type": "percent_of_sale_price", "rate": 5.005},
            advertisingCost={"type": "percent_of_sale_price", "rate": 3.005},
            otherCost={"type": "fixed", "amount": 0},
            targetMargin={"type": "percent_of_sale_price", "rate": 25},
        ),
    )

    assert result["proposedSalePrice"] == 10100
    assert result["expectedMarginRate"] >= 25.0


def test_calculated_price_must_fit_persisted_integer_summary_columns():
    with pytest.raises(PricingPolicyError, match="persistable range"):
        calculate_proposed_price(
            cost_price=8000,
            policy=_policy(
                shippingCost={"type": "fixed", "amount": 0},
                marketplaceFee={"type": "percent_of_sale_price", "rate": 49.999999},
                advertisingCost={"type": "percent_of_sale_price", "rate": 0},
                otherCost={"type": "fixed", "amount": 0},
                targetMargin={"type": "percent_of_sale_price", "rate": 50},
            ),
        )
