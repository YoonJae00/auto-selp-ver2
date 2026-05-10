import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from database import SessionLocal, Base, engine
from models import User
import uuid

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_user_model_creation():
    # 이 테스트는 실제 DB 연결이 필요합니다. 
    # 로컬 테스트 환경에서는 .env의 DATABASE_URL이 localhost를 가리켜야 합니다.
    # 여기서는 모델 정의가 올바른지 확인하는 수준으로 작성합니다.
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        username="testuser",
        hashed_password="hashed_password",
        is_admin=False,
        encrypted_api_keys={"naver": "encrypted_key"}
    )
    
    assert user.username == "testuser"
    assert user.id == user_id
    assert user.is_admin is False
    assert user.encrypted_api_keys["naver"] == "encrypted_key"
