from __future__ import annotations

from app.crawlers.yaml_adapter import (
    _image_csv,
    _is_placeholder_src,
    _supported_image_url,
)


def test_supported_image_url_extensions() -> None:
    assert _supported_image_url("https://cdn.x.com/a/b.jpg") == "https://cdn.x.com/a/b.jpg"
    assert _supported_image_url("https://cdn.x.com/a/b.GIF") == "https://cdn.x.com/a/b.GIF"
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


def test_image_csv_filters_and_joins() -> None:
    assert _image_csv([
        "https://x.com/a.jpg",
        "https://x.com/spacer.gif",  # junk → dropped
        "https://x.com/data/goods/9",  # extensionless → kept
    ]) == "https://x.com/a.jpg,https://x.com/data/goods/9"
    assert _image_csv([]) is None
