from __future__ import annotations

from app.crawlers.yaml_adapter import (
    _image_csv,
    _image_key,
    _image_values,
    _is_placeholder_src,
    _supported_image_url,
    _without_images,
)


def test_image_key_merges_size_variants() -> None:
    # 같은 그림의 썸네일/원본이 같은 키가 되어야 dedup이 성립.
    assert _image_key("https://x.com/big/103.jpg") == _image_key("https://x.com/small/103_s.jpg")
    assert _image_key("/img/103.jpg?w=200") == _image_key("/img/thumb_103.jpg")
    assert _image_key("https://x.com/a/103_thumb.png") == _image_key("https://x.com/b/103.png")
    # 사이즈 디렉토리만 다른 동일 파일명도 같은 키.
    assert _image_key("https://x.com/goods/big/9.jpg") == _image_key("https://x.com/goods/thumb/9.jpg")


def test_image_key_keeps_distinct_numeric_parts() -> None:
    # 숫자 식별부가 다르면 과잉 병합하지 않는다.
    assert _image_key("https://x.com/103.jpg") != _image_key("https://x.com/104.jpg")
    assert _image_key("/p/103_s.jpg") != _image_key("/p/104_s.jpg")


def test_supported_image_url_extensions() -> None:
    assert _supported_image_url("https://cdn.x.com/a/b.jpg") == "https://cdn.x.com/a/b.jpg"
    assert _supported_image_url("https://cdn.x.com/a/b.PNG") == "https://cdn.x.com/a/b.PNG"
    assert _supported_image_url("https://cdn.x.com/a/b.gif") is None  # gif excluded (banners/spacers)
    assert _supported_image_url("https://cdn.x.com/a/b.webp?w=800") == "https://cdn.x.com/a/b.webp?w=800"


def test_supported_image_url_extensionless_cdn() -> None:
    # CDN/resizer URLs with no file extension are now accepted.
    assert _supported_image_url("https://img.x.com/data/goods/view/12345") is not None
    assert _supported_image_url("https://img.x.com/resize?id=9&w=800") is not None


def test_supported_image_url_rejects_junk() -> None:
    assert _supported_image_url("data:image/gif;base64,R0lGOD") is None
    assert _supported_image_url("https://x.com/img/spacer.gif") is None
    assert _supported_image_url("https://x.com/blank.png") is None
    assert _supported_image_url("https://x.com/1x1.gif") is None
    assert _supported_image_url("https://x.com/no_image.jpg") is None
    assert _supported_image_url("https://x.com/assets/icon/cart.png") is None
    assert _supported_image_url("") is None
    assert _supported_image_url(None) is None


def test_is_placeholder_src() -> None:
    assert _is_placeholder_src("") is True
    assert _is_placeholder_src(None) is True
    assert _is_placeholder_src("data:image/gif;base64,AAAA") is True
    assert _is_placeholder_src("https://x.com/spacer.gif") is True
    assert _is_placeholder_src("https://x.com/real/photo.jpg") is False


def test_without_images_excludes_main_size_variants() -> None:
    # 대표이미지가 big/, 추가이미지 목록이 small/ 폴더여도 파일명이 같으면 제외
    images = ["https://x.com/goods/small/103.jpg", "https://x.com/goods/small/104.jpg"]
    assert _without_images(images, "https://x.com/goods/big/103.jpg") == ["https://x.com/goods/small/104.jpg"]
    # 상대경로 + 리사이저 쿼리도 동일 취급
    assert _without_images(["/img/103.jpg?w=200"], "https://x.com/img/103.jpg", "https://x.com/p") == []
    assert _without_images(images, None) == images


def test_image_csv_filters_and_joins() -> None:
    assert _image_csv([
        "https://x.com/a.jpg",
        "https://x.com/spacer.gif",  # junk → dropped
        "https://x.com/data/goods/9",  # extensionless → kept
    ]) == "https://x.com/a.jpg,https://x.com/data/goods/9"
    assert _image_csv([]) is None


def test_relative_src_is_absolutized_against_page_url() -> None:
    # 몰의 <img src>는 대개 상대경로 — page.url 기준으로 절대 URL이 되어야 한다.
    page_url = "http://localhost:9000/detail.html?product_no=401"
    assert _supported_image_url("assets/images/p_main.jpg", page_url) == "http://localhost:9000/assets/images/p_main.jpg"
    assert _image_values(["assets/images/a.jpg", "/b.png"], page_url) == [
        "http://localhost:9000/assets/images/a.jpg",
        "http://localhost:9000/b.png",
    ]
