import os
import logging
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    strava_id = Column(BigInteger, unique=True, index=True) # Unique ID from Strava
    date = Column(DateTime, default=datetime.datetime.utcnow)
    sport = Column(String)
    distance = Column(Float) # in km
    duration = Column(Integer) # in minutes
    coros_load = Column(Integer, nullable=True)
    avg_hr = Column(Float, nullable=True)

class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id = Column(BigInteger, primary_key=True, index=True) # Telegram User ID
    language = Column(String, default="en")
    last_active = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    """Creates all tables defined above if they don't exist."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ PostgreSQL Tables Initialized Successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize PostgreSQL: {e}")

def get_db():
    """Provides a transactional session to the database."""
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        logger.error(f"❌ Database Session Error: {e}")
    finally:
        db.close()