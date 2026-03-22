from __future__ import annotations

import httpx
import pytest_asyncio

from app.core.config import get_settings
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import import_model_modules
from app.infrastructure.db.session import get_engine, reset_db_state
from app.main import create_app


@pytest_asyncio.fixture
async def async_client(tmp_path, monkeypatch) -> httpx.AsyncClient:
    database_path = tmp_path / "caseflow-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("TEST_DATABASE_URL", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-with-32-plus-bytes")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("LOCAL_EMAIL_SINK_PATH", str(tmp_path / "emails"))

    get_settings.cache_clear()
    reset_db_state()
    import_model_modules()

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    reset_db_state()
    get_settings.cache_clear()
