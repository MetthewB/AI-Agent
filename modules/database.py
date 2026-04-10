import os
import logging
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Set up logging
logger = logging.getLogger(__name__)

# 1. Get the Database URL from environment
# Locally this will be your External URL, on Render it will be your Internal URL
DATABASE_URL = os.environ.get("DATABASE_URL")

# Fix for Render/Heroku which sometimes use 'postgres://' instead of 'postgresql://'
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 2. Setup the Engine and Session
# we use pool_pre_ping=True to handle database restarts/timeouts gracefully
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 📊 MODEL: Fitness Activity (Long-term history)
# ==========================================
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

# ==========================================
# ⚙️ MODEL: User Preferences (Language/Settings)
# ==========================================
class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id = Column(BigInteger, primary_key=True, index=True) # Telegram User ID
    language = Column(String, default="en")
    last_active = Column(DateTime, default=datetime.datetime.utcnow)

# ==========================================
# DATABASE UTILITIES
# ==========================================

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