import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
