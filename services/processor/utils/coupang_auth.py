import hmac
import hashlib
from datetime import datetime, timezone
from config import settings

def get_coupang_auth_header(method: str, path: str, query: str = "") -> dict:
    """
    Coupang API CEA Signature Generator
    Signature = HEX(HMAC-SHA256(timestamp + method + path + query, secret_key))
    """
    # ISO 8601 format: yyMMdd'T'HHmmss'Z'
    timestamp = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
    message = f"{timestamp}{method.upper()}{path}{query}"
    secret_key = settings.Coupang_Secret_Key.encode('utf-8')
    
    signature = hmac.new(secret_key, message.encode('utf-8'), hashlib.sha256).hexdigest()
    
    auth_header = (
        f"CEA algorithm=HmacSHA256, access-key={settings.Coupang_Access_Key}, "
        f"signed-date={timestamp}, signature={signature}"
    )
    
    return {"Authorization": auth_header}
