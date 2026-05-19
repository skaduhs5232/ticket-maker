from sqlalchemy import create_engine, MetaData, event
from sqlalchemy.orm import sessionmaker, declarative_base

from config import POSTGRES_URL, POSTGRES_SCHEMA

DATABASE_URL = POSTGRES_URL
SCHEMA = POSTGRES_SCHEMA

metadata = MetaData(schema=SCHEMA)
Base = declarative_base(metadata=metadata)

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

        @event.listens_for(_engine, "connect")
        def _set_search_path(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute(f'SET search_path TO {SCHEMA}, extensions, public')
            cursor.close()

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

