import os
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

# Database config
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 4000))
DB_DATABASE = os.getenv("DB_DATABASE")

# JWT config
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 60))

# Validations
if not DB_USERNAME or not DB_PASSWORD or not DB_HOST or not DB_DATABASE:
    raise ValueError("Database environment variables are missing. Check your .env file.")

if not JWT_SECRET:
    raise ValueError("JWT_SECRET is missing. Add it in your .env file.")
