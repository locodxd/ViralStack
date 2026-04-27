import logging
from sqlalchemy import text
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
    _ensure_v12_schema()
    logger.info("Database initialized at %s", settings.db_path)


def _ensure_v12_schema() -> None:
    """Add nullable v1.2 columns when an existing SQLite DB predates them."""
    additions = {
        "platforms_enabled_json": "TEXT",
        "platform_results_json": "TEXT",
        "platform_errors_json": "TEXT",
    }
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(videos)")).fetchall()
        existing = {row[1] for row in rows}
        for column, column_type in additions.items():
            if column not in existing:
                logger.info("Adding missing videos.%s column", column)
                connection.execute(text(f"ALTER TABLE videos ADD COLUMN {column} {column_type}"))


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
