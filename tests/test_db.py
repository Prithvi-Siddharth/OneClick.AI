from app.db import engine
from sqlalchemy import text

def test_connection():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print(result.fetchone())

if __name__ == "__main__":
    test_connection()