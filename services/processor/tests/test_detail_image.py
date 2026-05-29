import pytest
from utils.detail_image import extract_images_from_detail_content

def test_extract_images_from_detail_content_with_html():
    html_content = '<p>Test</p><img src="http://example.com/img1.jpg"><img src="https://example.com/img2.png">'
    result = extract_images_from_detail_content(html_content)
    assert result == ["http://example.com/img1.jpg", "https://example.com/img2.png"]

def test_extract_images_from_detail_content_with_url():
    url_content = "http://example.com/single_image.jpg"
    result = extract_images_from_detail_content(url_content)
    assert result == ["http://example.com/single_image.jpg"]

def test_extract_images_from_detail_content_empty():
    assert extract_images_from_detail_content(None) == []
    assert extract_images_from_detail_content("") == []
