from utils.product_name import generate_product_name


def test_overlapping_keywords_keep_useful_order():
    assert generate_product_name(["작업 발판", "발판 사다리"], "무시") == "작업 발판 사다리"


def test_overlap_can_prepend_to_keep_subject_first():
    assert generate_product_name(["발판 사다리", "작업 발판"], "무시") == "작업 발판 사다리"


def test_repetition_limit_is_casefolded_and_preserves_spelling():
    name = generate_product_name(["Pro pro PRO ladder"], "무시")
    assert name == "Pro pro ladder"
    assert sum(token.casefold() == "pro" for token in name.split()) == 2


def test_bounds_and_cleanup():
    name = generate_product_name(
        ["ＡＣＭＥ!!  작업__발판", "사다리", "초경량", "접이식", "실내용", "안전", "미끄럼방지", "높이조절", "알루미늄", "보관"],
        "무시",
        "acme",
    )
    assert "ＡＣＭＥ" not in name
    assert len(name.split()) <= 9
    assert len(name) <= 50
    assert all(name.casefold().split().count(token) <= 2 for token in name.casefold().split())

    long_name = generate_product_name(
        ["abcdefghij", "klmnopqrst", "uvwxyzabcd", "efghijklmn", "opqrstuvwx"], "무시"
    )
    assert len(long_name) <= 50


def test_brand_duplicate_contained_and_fallback_are_excluded():
    assert generate_product_name(["Acme 작업 발판", "작업 발판", "발판"], "Acme 접이식 발판", "ACME") == "작업 발판"
    assert generate_product_name([], "ACME", "acme", "ACME 원본 사다리") == "원본 사다리"
    assert generate_product_name([], "ACME", "acme", "ACME") == ""
    assert generate_product_name([], "x" * 51, original_name="원본 사다리") == "원본 사다리"


def test_product_name_is_deterministic():
    values = ["작업 발판", "발판 사다리", "접이식"]
    assert generate_product_name(values, "무시") == generate_product_name(values, "무시")
