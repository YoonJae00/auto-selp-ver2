from schemas import MarketAccountCreate, MarketAccountSettingsUpdate


def test_market_account_create_fields_contract():
    assert set(MarketAccountCreate.model_fields.keys()) == {
        "market_code",
        "display_name",
        "credentials",
    }


def test_market_account_settings_update_default_schema_version():
    assert MarketAccountSettingsUpdate().settings_schema_version == "v1"
