import pytest
from utils.naver_auth import get_naver_ad_header
from utils.coupang_auth import get_coupang_auth_header

def test_naver_ad_header():
    method = "GET"
    uri = "/keywordstool"
    headers = get_naver_ad_header(method, uri)
    
    assert "X-Timestamp" in headers
    assert "X-API-KEY" in headers
    assert "X-Customer" in headers
    assert "X-Signature" in headers
    assert len(headers["X-Signature"]) > 0

def test_coupang_auth_header():
    method = "POST"
    path = "/v2/providers/openapi/apis/api/v1/categorization/predict"
    headers = get_coupang_auth_header(method, path)
    
    assert "Authorization" in headers
    assert "CEA algorithm=HmacSHA256" in headers["Authorization"]
    assert "signature=" in headers["Authorization"]
    assert "signed-date=" in headers["Authorization"]
