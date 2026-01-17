from fastapi import FastAPI
from app.db.session import engine, Base
from app.models.user import User
from app.db.session import get_db


#creates an app
app = FastAPI(title="ML SaaS Platform")

#this command connects to the tidb and creates a table from the structure defined earlier
Base.metadata.create_all(bind=engine)

@app.get("/")
def read_root():
    return {"message": "Hello World"}

