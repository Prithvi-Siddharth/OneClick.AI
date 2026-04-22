import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

#DB environment variables
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_SSL_CA = os.getenv("DB_SSL_CA")

if not all([DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_SSL_CA, DB_NAME]):
    raise RuntimeError("One or more DB environment variables are missing")

#DB connection
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SSL_CA_PATH = os.path.join(BASE_DIR, DB_SSL_CA)

#DB connection string
DATABASE_URL = (
    f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?ssl_ca={SSL_CA_PATH}"
)

#DB engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

#DB session 
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# DB Session helper
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()