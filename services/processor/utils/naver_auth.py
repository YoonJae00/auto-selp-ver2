import time
import base64
import hmac
import hashlib
from config import settings

def get_naver_ad_header(method: str, uri: str) -> dict:
    """
    Naver Search Ad API HMAC Signature Generator
    Signature = Base64(HMAC-SHA256(timestamp + "." + method + "." + uri, secret_key))
    """
    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}.{method.upper()}.{uri}"
    secret_key = settings.NAVER_SECRET_KEY.encode('utf-8')
    
    signature = hmac.new(secret_key, message.encode('utf-8'), hashlib.sha256).digest()
    signature_base64 = base64.b64encode(signature).decode('utf-8')
    
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": settings.NAVER_API_KEY,
        "X-Customer": settings.NAVER_CUSTOMER_ID,
        "X-Signature": signature_base64
    }
