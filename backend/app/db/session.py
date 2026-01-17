from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

from app.core.config import (
    DB_USERNAME,
    DB_PASSWORD,
    DB_HOST,
    DB_PORT,
    DB_DATABASE
)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

CA_CERT_PATH = os.path.join(BASE_DIR, "backend", "certs", "tidb-ca.pem")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_DATABASE}"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "ssl": {
            "ca": CA_CERT_PATH
        }
    },
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
