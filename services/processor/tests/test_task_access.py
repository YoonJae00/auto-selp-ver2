import os
import uuid

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "internal-test-token")
for key in (
    "NAVER_API_KEY",
    "NAVER_SECRET_KEY",
    "NAVER_CUSTOMER_ID",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "Coupang_Access_Key",
    "Coupang_Secret_Key",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
):
    os.environ.setdefault(key, "test")

import main


class MissingTaskResult:
    def scalar_one_or_none(self):
        return None


class MissingTaskDB:
    async def execute(self, _statement):
        return MissingTaskResult()


@pytest.mark.anyio
async def test_status_and_download_hide_tasks_not_owned_by_current_user():
    current_user = {"id": uuid.uuid4()}
    db = MissingTaskDB()

    for endpoint in (main.get_status, main.download_result):
        with pytest.raises(HTTPException) as error:
            await endpoint("another-users-task", current_user, db)
        assert error.value.status_code == 404
