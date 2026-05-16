import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("POSTGRES_URL", "")

Base = declarative_base()

# Engine and session are lazily created so the app can start even if the
# database is not yet configured (e.g., first boot before migrations).
_engine = None
_SessionLocal = None


def _get_engine():
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "POSTGRES_URL not set. Please configure it in the .env file."
            )
        _engine = create_engine(DATABASE_URL)
    return _engine


def get_db():
    engine = _get_engine()
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()

