import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from models import Base

# Get database URL from environment, fallback to SQLite for local dev
SQLALCHEMY_DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'sqlite:///./booking.db'
)

# PostgreSQL doesn't need check_same_thread
connect_args = {}
if SQLALCHEMY_DATABASE_URL.startswith('sqlite'):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db(target_engine=None):
    """Create all database tables defined in `models` if they do not already exist,
    and apply lightweight migrations (such as missing columns).
    """
    eng = target_engine if target_engine is not None else engine
    Base.metadata.create_all(bind=eng)
    inspector = inspect(eng)
    if "bookings" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("bookings")]
        if "itinerary_id" not in columns:
            with eng.connect() as conn:
                conn.execute(text("ALTER TABLE bookings ADD COLUMN itinerary_id INTEGER REFERENCES itineraries(id)"))
                conn.commit()

def get_db():
    """Yield a database session for use as a FastAPI dependency.

    The session is always closed after the request completes, even if the
    request handler fails.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()