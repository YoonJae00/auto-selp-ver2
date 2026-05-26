from sqlalchemy import Float, Integer, UniqueConstraint

from models import (
    MarketAccount,
    MarketAccountSettings,
    MarketDraftGenerationJob,
    MarketListingDraft,
)


def test_model_table_names():
    assert MarketAccount.__tablename__ == "market_accounts"
    assert MarketAccountSettings.__tablename__ == "market_account_settings"
    assert MarketDraftGenerationJob.__tablename__ == "market_draft_generation_jobs"
    assert MarketListingDraft.__tablename__ == "market_listing_drafts"


def test_market_listing_draft_required_columns_exist():
    column_names = set(MarketListingDraft.__table__.columns.keys())

    assert "cost_price" in column_names
    assert "sale_price" in column_names
    assert "expected_profit" in column_names
    assert "expected_margin_rate" in column_names
    assert "generated_payload" in column_names
    assert "override_patch" in column_names
    assert "recipe_versions" in column_names


def test_market_listing_draft_numeric_column_types():
    sale_price_col = MarketListingDraft.__table__.columns["sale_price"]
    cost_price_col = MarketListingDraft.__table__.columns["cost_price"]
    expected_profit_col = MarketListingDraft.__table__.columns["expected_profit"]
    expected_margin_rate_col = MarketListingDraft.__table__.columns["expected_margin_rate"]

    assert isinstance(sale_price_col.type, Integer)
    assert isinstance(cost_price_col.type, Integer)
    assert isinstance(expected_profit_col.type, Integer)
    assert isinstance(expected_margin_rate_col.type, Float)


def test_market_listing_draft_json_required_fields_not_nullable():
    validation_result_col = MarketListingDraft.__table__.columns["validation_result"]
    recipe_versions_col = MarketListingDraft.__table__.columns["recipe_versions"]

    assert validation_result_col.nullable is False
    assert recipe_versions_col.nullable is False


def test_market_account_has_no_user_market_unique_constraint():
    constraints = [
        c
        for c in MarketAccount.__table__.constraints
        if isinstance(c, UniqueConstraint)
    ]

    user_market_constraints = [
        c
        for c in constraints
        if tuple(col.name for col in c.columns) == ("user_id", "market_code")
    ]
    assert user_market_constraints == []
