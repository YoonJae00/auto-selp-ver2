import pytest


def test_product_processor_graph_import_surface():
    from graphs.product_processor import (
        ProductProcessingContext,
        build_product_processing_graph,
        process_product_with_graph,
    )

    assert ProductProcessingContext is not None
    assert callable(build_product_processing_graph)
    assert callable(process_product_with_graph)
