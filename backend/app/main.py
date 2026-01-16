from fastapi import FastAPI

app = FastAPI(title="ML SaaS Platform")

@app.get("/")
def read_root():
    return {"message": "Hello World"}