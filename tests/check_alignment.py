from app.db import SessionLocal
from app.models import User, Experiment

def check_users_and_models():
    db = SessionLocal()
    users = db.query(User).all()
    print("--- Users in DB ---")
    for u in users:
        print(f"Username: {u.username}, UserID (primary key): {u.user_id}")
        
    experiments = db.query(Experiment).all()
    print("\n--- Experiments in DB ---")
    for e in experiments:
        print(f"Model: {e.name}, Linked UserID: {e.user_id}")
    db.close()

if __name__ == "__main__":
    check_users_and_models()
