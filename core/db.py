import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from config.settings import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30},
)


# Enable SQLite WAL mode + sane pragmas on every new connection.
# WAL mode allows concurrent readers while a writer is active, which
# matches the workload of this app (FastAPI dashboard + scheduler).
@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
    try:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.execute("PRAGMA busy_timeout=30000;")
        cur.close()
    except Exception as e:
        logger.warning("Failed to apply SQLite pragmas: %s", e)


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    """Create all tables if they don't exist."""
    from core.models import Base
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized at %s", settings.db_path)


@contextmanager
def get_session() -> Session:
    """Context manager for database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
