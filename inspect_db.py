import sys
import os
from sqlalchemy import text

# Add the backend directory and tests directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'tests')))

from app.db import get_db

def inspect():
    db = next(get_db())
    with open("db_schema.txt", "w") as f:
        f.write("-" * 50 + "\n")
        f.write("TABLES:\n")
        res = db.execute(text("SHOW TABLES;"))
        for r in res:
            f.write(f" - {r[0]}\n")
        
        for table in ['datasets', 'experiments', 'folders', 'temp']:
            f.write(f"\nSCHEMA FOR {table.upper()}:\n")
            try:
                res = db.execute(text(f"SHOW COLUMNS FROM {table};"))
                for r in res:
                    f.write(f" {r[0]} ({r[1]}) - Null: {r[2]}, Key: {r[3]}, Default: {r[4]}\n")
            except Exception as e:
                f.write(f" ERROR: {e}\n")
            
    db.close()

if __name__ == "__main__":
    inspect()
