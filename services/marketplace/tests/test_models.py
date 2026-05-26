from sqlalchemy import Float, Integer, UniqueConstraint

from models import (
    MarketAccount,
    MarketAccountSettings,
    MarketDraftGenerationJob,
    MarketListingDraft,
)


def test_marketplace_models_use_distinct_owned_tables():
    assert MarketAccount.__tablename__ == "market_accounts"
    assert MarketAccountSettings.__tablename__ == "market_account_settings"
    assert MarketDraftGenerationJob.__tablename__ == "market_draft_generation_jobs"
    assert MarketListingDraft.__tablename__ == "market_listing_drafts"


def test_market_listing_draft_required_columns_exist():
    column_names = set(MarketListingDraft.__table__.columns.keys())

    assert {
        "id",
        "source_product_id",
        "source_user_id",
        "source_product_version",
        "market_account_id",
        "market_code",
        "status",
        "cost_price",
        "sale_price",
        "expected_profit",
        "expected_margin_rate",
        "generated_payload",
        "override_patch",
        "validation_result",
        "recipe_versions",
        "created_at",
        "updated_at",
    }.issubset(column_names)


def test_market_listing_draft_required_json_output_columns_not_nullable():
    generated_payload_col = MarketListingDraft.__table__.columns["generated_payload"]
    validation_result_col = MarketListingDraft.__table__.columns["validation_result"]
    recipe_versions_col = MarketListingDraft.__table__.columns["recipe_versions"]

    assert generated_payload_col.nullable is False
    assert validation_result_col.nullable is False
    assert recipe_versions_col.nullable is False


def test_market_listing_draft_numeric_column_types():
    sale_price_col = MarketListingDraft.__table__.columns["sale_price"]
    cost_price_col = MarketListingDraft.__table__.columns["cost_price"]
    expected_profit_col = MarketListingDraft.__table__.columns["expected_profit"]
    expected_margin_rate_col = MarketListingDraft.__table__.columns["expected_margin_rate"]

    assert isinstance(sale_price_col.type, Integer)
    assert isinstance(cost_price_col.type, Integer)
    assert isinstance(expected_profit_col.type, Integer)
    assert isinstance(expected_margin_rate_col.type, Float)


def test_market_listing_draft_has_no_unconditional_active_uniqueness_constraint():
    constraints = [
        c
        for c in MarketListingDraft.__table__.constraints
        if isinstance(c, UniqueConstraint)
    ]
    active_constraints = [
        c
        for c in constraints
        if tuple(col.name for col in c.columns)
        == ("source_product_id", "market_account_id", "draft_kind")
    ]
    assert active_constraints == []


def test_market_listing_draft_has_partial_unique_index_for_active_statuses():
    indexes = list(MarketListingDraft.__table__.indexes)
    target_indexes = [
        idx
        for idx in indexes
        if tuple(col.name for col in idx.columns)
        == ("source_product_id", "market_account_id", "draft_kind")
        and idx.unique
    ]
    assert target_indexes, "missing partial unique active-draft index"

    index = target_indexes[0]
    where_clause = str(index.dialect_options["postgresql"]["where"])
    assert "generated" in where_clause
    assert "needs_review" in where_clause
    assert "ready" in where_clause
    assert "submitting" in where_clause
    assert "failed" in where_clause
    assert "submitted" not in where_clause


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

    user_market_unique_indexes = [
        idx
        for idx in MarketAccount.__table__.indexes
        if tuple(col.name for col in idx.columns) == ("user_id", "market_code")
        and idx.unique
    ]
    assert user_market_unique_indexes == []
