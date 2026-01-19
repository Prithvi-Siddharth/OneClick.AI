#custom SQL tool to interact with the database from the terminal
#run this file using python debug_db.py
#use this to check the database tables and data

from app.db import get_db
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

def run_sql_terminal():
    # Get a session
    db = next(get_db())
    print("-" * 50)
    print("Welcome to the SQL Terminal.")
    print("Type your SQL query and press Enter.")
    print("Type 'exit' or 'quit' to stop.")
    print("-" * 50)

    while True:
        try:
            sql_input = input("\nSQL> ").strip()
            
            if sql_input.lower() in ['exit', 'quit']:
                print("Exiting...")
                break
            
            if not sql_input:
                continue

            # Execute the query
            try:
                result = db.execute(text(sql_input))
                
                # Check if the query returns rows (e.g., SELECT)
                if result.returns_rows:
                    rows = result.fetchall()
                    if not rows:
                        print("No results found.")
                    else:
                        # Print headers
                        headers = result.keys()
                        print(" | ".join(headers))
                        print("-" * (len(" | ".join(headers))))
                        
                        # Print rows
                        for row in rows:
                            print(" | ".join(str(val) for val in row))
                else:
                    # For INSERT, UPDATE, DELETE, etc.
                    db.commit()
                    print(f"Query executed successfully. Rows affected: {result.rowcount}")

            except SQLAlchemyError as e:
                db.rollback()
                print(f"SQL Error: {e}")
            except Exception as e:
                print(f"Error: {e}")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
            
    db.close()

if __name__ == "__main__":
    run_sql_terminal()
