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
    columns = set(MarketListingDraft.__table__.columns.keys())

    assert {
        "id",
        "source_product_id",
        "source_user_id",
        "market_account_id",
        "market_code",
        "status",
        "generated_payload",
        "validation_result",
        "created_at",
        "updated_at",
    }.issubset(columns)
