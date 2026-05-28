from schemas import (
    MarketAccountCreate,
    MarketAccountResponse,
    MarketAccountSettingsUpdate,
)


def test_market_account_create_fields_contract():
    assert set(MarketAccountCreate.model_fields.keys()) == {
        "market_code",
        "display_name",
        "credentials",
    }


def test_market_account_settings_update_default_schema_version():
    assert MarketAccountSettingsUpdate().settings_schema_version == "v1"


def test_market_account_response_exposes_only_public_fields():
    field_names = set(MarketAccountResponse.model_fields.keys())

    assert "user_id" not in field_names
    assert "credentials" not in field_names
    assert "credentials_encrypted" not in field_names
