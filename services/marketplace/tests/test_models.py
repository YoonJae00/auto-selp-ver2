import uuid

from sqlalchemy import Float, Integer, UniqueConstraint, create_engine, event, select
from sqlalchemy.orm import Session

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


def test_market_account_and_job_user_id_are_non_nullable():
    account_user_id_col = MarketAccount.__table__.columns["user_id"]
    job_user_id_col = MarketDraftGenerationJob.__table__.columns["user_id"]

    assert account_user_id_col.nullable is False
    assert job_user_id_col.nullable is False


def test_market_account_related_foreign_keys_use_cascade_delete():
    settings_fk = next(iter(MarketAccountSettings.__table__.columns["market_account_id"].foreign_keys))
    draft_fk = next(iter(MarketListingDraft.__table__.columns["market_account_id"].foreign_keys))

    assert settings_fk.target_fullname == "market_accounts.id"
    assert settings_fk.ondelete == "CASCADE"
    assert draft_fk.target_fullname == "market_accounts.id"
    assert draft_fk.ondelete == "CASCADE"


def test_market_listing_draft_required_columns_exist():
    column_names = set(MarketListingDraft.__table__.columns.keys())

    assert "cost_price" in column_names
    assert "sale_price" in column_names
    assert "expected_profit" in column_names
    assert "expected_margin_rate" in column_names
    assert "generated_payload" in column_names
    assert "override_patch" in column_names
    assert "recipe_versions" in column_names


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


def test_market_account_drafts_relationship_uses_passive_deletes():
    drafts_relationship = MarketAccount.__mapper__.relationships["drafts"]

    assert drafts_relationship.passive_deletes == "all"


def test_deleting_account_with_loaded_drafts_relies_on_fk_cascade_without_nullifying_updates():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    MarketAccount.__table__.create(bind=engine)
    MarketAccountSettings.__table__.create(bind=engine)
    MarketListingDraft.__table__.create(bind=engine)

    account_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    with Session(engine) as session:
        account = MarketAccount(
            id=account_id,
            user_id=uuid.uuid4(),
            market_code="naver",
            display_name="Main account",
            credentials_encrypted="enc",
        )
        draft = MarketListingDraft(
            id=draft_id,
            source_product_id=uuid.uuid4(),
            source_product_version="v1",
            market_account_id=account_id,
            market_code="naver",
            source_snapshot={},
            generated_payload={},
            validation_result={},
            recipe_versions={},
            adapter_version="adapter-v1",
        )
        session.add(account)
        session.add(draft)
        session.commit()

    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    try:
        with Session(engine) as session:
            account = session.get(MarketAccount, account_id)
            assert account is not None
            assert len(account.drafts) == 1

            session.delete(account)
            session.commit()

        with Session(engine) as session:
            assert session.scalar(
                select(MarketListingDraft).where(MarketListingDraft.id == draft_id)
            ) is None
    finally:
        event.remove(engine, "before_cursor_execute", _capture_sql)
        event.remove(engine, "connect", _enable_sqlite_fk)
        engine.dispose()

    nullify_updates = [
        stmt
        for stmt in statements
        if "UPDATE market_listing_drafts" in stmt and "market_account_id" in stmt
    ]
    assert not nullify_updates
