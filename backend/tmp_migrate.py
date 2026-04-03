import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load .env from the root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_SSL_CA = os.getenv("DB_SSL_CA")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SSL_CA_PATH = os.path.join(BASE_DIR, DB_SSL_CA)

DATABASE_URL = (
    f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?ssl_ca={SSL_CA_PATH}"
)

engine = create_engine(DATABASE_URL)

def migrate():
    with engine.connect() as connection:
        print("Checking for profile_pic_url column in users table...")
        try:
            # Check if column exists
            result = connection.execute(text("SHOW COLUMNS FROM users LIKE 'profile_pic_url'"))
            column_exists = result.fetchone() is not None
            
            if not column_exists:
                print("Adding profile_pic_url column...")
                connection.execute(text("ALTER TABLE users ADD COLUMN profile_pic_url VARCHAR(1024) NULL AFTER password"))
                connection.commit()
                print("Column added successfully!")
            else:
                print("Column already exists.")
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
