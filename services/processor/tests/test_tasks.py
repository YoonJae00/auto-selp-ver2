import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("NAVER_API_KEY", "test")
os.environ.setdefault("NAVER_SECRET_KEY", "test")
os.environ.setdefault("NAVER_CUSTOMER_ID", "test")
os.environ.setdefault("NAVER_CLIENT_ID", "test")
os.environ.setdefault("NAVER_CLIENT_SECRET", "test")
os.environ.setdefault("Coupang_Access_Key", "test")
os.environ.setdefault("Coupang_Secret_Key", "test")
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("KIPRIS_API_KEY", "test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")

from tasks import _run_pipeline

@pytest.fixture
def sample_excel(tmp_path):
    df = pd.DataFrame({
        "original_name": ["Product 1", "Product 2"]
    })
    file_path = tmp_path / "test.xlsx"
    df.to_excel(file_path, index=False)
    return str(file_path)

@pytest.mark.asyncio
async def test_run_pipeline_propagates_warnings(sample_excel):
    mock_task = MagicMock()
    column_mapping = {"original_name": "original_name"}
    
    # Mock dependencies
    with patch("tasks.SessionLocal") as mock_session_class, \
         patch("tasks.get_llm_client") as mock_get_llm, \
         patch("tasks.KeywordEngine") as mock_keyword_engine_class, \
         patch("tasks.CategoryMapper") as mock_category_mapper_class:
        
        # Setup session mock
        mock_db = AsyncMock()
        mock_session_class.return_value.__aenter__.return_value = mock_db
        
        # Setup LLM client mock
        mock_llm = AsyncMock()
        mock_llm.refine_product_name.return_value = "Refined Name"
        mock_get_llm.return_value = mock_llm
        
        # Setup KeywordEngine mock
        mock_keyword_engine = mock_keyword_engine_class.return_value
        mock_keyword_engine.curate_keywords = AsyncMock(side_effect=[
            (["kw1"], [{"keyword": "kw1", "info": {"exists": True}}]),
            (["kw2"], [])
        ])
        
        # Setup CategoryMapper mock
        mock_category_mapper = mock_category_mapper_class.return_value
        mock_category_mapper.get_naver_category = AsyncMock(return_value={"id": "cat1"})
        mock_category_mapper.get_coupang_category = AsyncMock(return_value="cat2")
        
        # Run pipeline
        result = await _run_pipeline(mock_task, sample_excel, column_mapping, "gemini")
        
        # Verify update_state calls
        assert mock_task.update_state.called
        
        # Find the last update_state call or check all of them
        # We expect 'warnings' to be in meta
        update_calls = mock_task.update_state.call_args_list
        
        # Check if any call contains warnings
        warnings_found = False
        for call in update_calls:
            args, kwargs = call
            meta = kwargs.get('meta', {})
            if 'warnings' in meta:
                warnings_found = True
                # Check structure of warnings
                # For row 0, it should have a warning. For row 1, empty.
                # Since _run_pipeline is supposed to accumulate them:
                # After row 0: warnings = {0: [...]}
                # After row 1: warnings = {0: [...], 1: []}
                if meta['current'] == 1:
                    assert 0 in meta['warnings']
                    assert meta['warnings'][0][0]['keyword'] == "kw1"
                elif meta['current'] == 2:
                    assert 0 in meta['warnings']
                    assert 1 not in meta['warnings']

        assert warnings_found, "Warnings not found in task metadata"

    # Cleanup processed file
    processed_path = sample_excel.replace(".xlsx", "_processed.xlsx")
    if os.path.exists(processed_path):
        os.remove(processed_path)


@pytest.mark.asyncio
async def test_run_db_pipeline_delegates_products_to_langgraph_and_preserves_progress_shape():
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch
    from tasks import _run_db_pipeline

    import_id = uuid.uuid4()
    product_id = uuid.uuid4()
    another_product_id = uuid.uuid4()
    import_run = SimpleNamespace(
        id=import_id,
        status="pending",
        success_count=0,
        failed_count=0,
    )
    product = SimpleNamespace(
        id=product_id,
        original_name="원본 상품명",
        status="pending",
    )
    another_product = SimpleNamespace(
        id=another_product_id,
        original_name="두번째 상품명",
        status="pending",
    )

    class FakeResult:
        def __init__(self, scalar=None, scalars=None):
            self.scalar = scalar
            self.scalars_value = scalars or []

        def scalar_one_or_none(self):
            return self.scalar

        def scalars(self):
            return self

        def all(self):
            return self.scalars_value

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[
        FakeResult(scalar=import_run),
        FakeResult(scalars=[product, another_product]),
    ])

    mock_task = MagicMock()

    marketplace_client = object()
    seen_marketplace_clients = []

    async def fake_process_product_with_graph(context):
        assert context.product is product or context.product is another_product
        assert context.import_run is import_run
        seen_marketplace_clients.append(context.marketplace_client)
        context.completed_rows.append({"name": context.product.original_name, "stages": []})
        context.all_warnings[context.row_index] = [{"keyword": "브랜드"}]
        context.import_run.success_count += 1
        return {"refined_name": "정제 상품명"}

    with patch("tasks.SessionLocal") as mock_session_class, \
         patch("tasks.get_llm_client") as mock_get_llm, \
         patch("tasks.KeywordEngine") as mock_keyword_engine_class, \
         patch("tasks.CategoryMapper") as mock_category_mapper_class, \
         patch("tasks.MarketplaceClient", return_value=marketplace_client) as mock_marketplace_client_class, \
         patch("tasks.process_product_with_graph", side_effect=fake_process_product_with_graph) as mock_graph:
        mock_session_class.return_value.__aenter__.return_value = mock_db
        mock_get_llm.return_value = object()
        mock_keyword_engine_class.return_value = object()
        mock_category_mapper_class.return_value = object()

        result = await _run_db_pipeline(mock_task, str(import_id), {}, "gemini", True)

    assert result["status"] == "Completed"
    assert result["total"] == 2
    assert mock_graph.await_count == 2
    assert import_run.status == "completed"
    mock_marketplace_client_class.assert_called_once_with()
    assert seen_marketplace_clients == [marketplace_client, marketplace_client]

    progress_meta = mock_task.update_state.call_args.kwargs["meta"]
    assert set(progress_meta) == {
        "percent",
        "current",
        "total",
        "stage",
        "current_name",
        "completed_rows",
        "warnings",
    }
    assert progress_meta["stage"] == "completed_row"
    assert progress_meta["percent"] == 100
    assert [row["name"] for row in progress_meta["completed_rows"]] == ["원본 상품명", "두번째 상품명"]
