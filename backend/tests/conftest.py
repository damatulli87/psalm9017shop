import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Must happen BEFORE any `app.*` import: app.config reads DATABASE_URL at
# Settings() instantiation time. Tests get their own SQLite file so running
# the suite never writes test data (or test-induced Approval/AuditEvent
# rows) into the real dev database the owner is actually using.
_TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_ultron.db"
_TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"

import pytest

from app.bootstrap import bootstrap
from app.database import Base, SessionLocal, engine


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        bootstrap(db)
    finally:
        db.close()
    yield
    engine.dispose()
    _TEST_DB_PATH.unlink(missing_ok=True)
