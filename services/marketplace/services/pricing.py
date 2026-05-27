from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP


class PricingPolicyError(ValueError):
    """Raised when a price cannot safely be derived from account policy."""


ZERO = Decimal("0")
ONE = Decimal("1")
ONE_HUNDRED = Decimal("100")


def _decimal(value, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PricingPolicyError(f"{field_name} must be numeric") from exc
    if not amount.is_finite():
        raise PricingPolicyError(f"{field_name} must be numeric")
    return amount


def _fixed_amount(component: dict | None, field_name: str) -> Decimal:
    if component is None:
        return ZERO
    if component.get("type") != "fixed":
        raise PricingPolicyError(f"{field_name} must be a fixed amount")
    amount = _decimal(component.get("amount", 0), field_name)
    if amount < ZERO or amount != amount.to_integral_value():
        raise PricingPolicyError(f"{field_name} must be a non-negative whole-won amount")
    return amount


def _percent_rate(
    component: dict | None, field_name: str, *, required: bool = False
) -> Decimal:
    if component is None:
        if required:
            raise PricingPolicyError(f"{field_name} is required")
        return ZERO
    if component.get("type") != "percent_of_sale_price":
        raise PricingPolicyError(f"{field_name} must be percent_of_sale_price")
    rate = _decimal(component.get("rate", 0), field_name)
    if rate < ZERO:
        raise PricingPolicyError(f"{field_name} rate must be non-negative")
    return rate / ONE_HUNDRED


def _other_cost_components(component: dict | None) -> tuple[Decimal, Decimal]:
    if component is None:
        return ZERO, ZERO
    if component.get("type") == "fixed":
        return _fixed_amount(component, "otherCost"), ZERO
    if component.get("type") == "percent_of_sale_price":
        return ZERO, _percent_rate(component, "otherCost")
    raise PricingPolicyError("otherCost must be fixed or percent_of_sale_price")


def _won(value: Decimal) -> int:
    return int(value.quantize(ONE, rounding=ROUND_HALF_UP))


def calculate_proposed_price(cost_price: int | None, policy: dict | None) -> dict:
    if policy is None:
        raise PricingPolicyError("pricing policy is required")
    if cost_price is None:
        raise PricingPolicyError("cost price is required")

    cost = _decimal(cost_price, "cost price")
    if cost <= ZERO or cost != cost.to_integral_value():
        raise PricingPolicyError("cost price must be positive whole won")

    shipping_cost = _fixed_amount(policy.get("shippingCost"), "shippingCost")
    marketplace_rate = _percent_rate(policy.get("marketplaceFee"), "marketplaceFee")
    advertising_rate = _percent_rate(policy.get("advertisingCost"), "advertisingCost")
    other_fixed, other_rate = _other_cost_components(policy.get("otherCost"))
    target_rate = _percent_rate(
        policy.get("targetMargin"), "targetMargin", required=True
    )

    rate_total = marketplace_rate + advertising_rate + other_rate + target_rate
    if rate_total >= ONE:
        raise PricingPolicyError("percentage rates must total less than 100")

    rounding = policy.get("rounding") or {"unit": 1, "mode": "ceil"}
    if rounding.get("mode", "ceil") != "ceil":
        raise PricingPolicyError("rounding mode must be ceil")
    unit = _decimal(rounding.get("unit", 1), "rounding unit")
    if unit <= ZERO or unit != unit.to_integral_value():
        raise PricingPolicyError("rounding unit must be a positive whole-won amount")

    raw_price = (cost + shipping_cost + other_fixed) / (ONE - rate_total)
    sale_price = int((raw_price / unit).to_integral_value(rounding=ROUND_CEILING) * unit)
    sale = Decimal(sale_price)
    marketplace_fee = _won(sale * marketplace_rate)
    advertising_cost = _won(sale * advertising_rate)
    other_cost = _won(other_fixed + (sale * other_rate))
    expected_profit = (
        sale_price
        - int(cost)
        - int(shipping_cost)
        - marketplace_fee
        - advertising_cost
        - other_cost
    )
    expected_margin_rate = float(
        ((Decimal(expected_profit) / sale) * ONE_HUNDRED).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )

    return {
        "policyVersion": policy.get("version", "pricing:v1"),
        "costPrice": int(cost),
        "proposedSalePrice": sale_price,
        "shippingCost": int(shipping_cost),
        "marketplaceFee": marketplace_fee,
        "advertisingCost": advertising_cost,
        "otherCost": other_cost,
        "expectedProfit": expected_profit,
        "expectedMarginRate": expected_margin_rate,
    }
