import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware


from app.db import engine
from app.models import Base, User
from app.db import get_db
from sqlalchemy.orm import Session
from fastapi import Depends
from app.security import get_current_user_id

# Import all routers
from app.routers import auth, dashboard, data_catalog, model_catalog, preprocessing, training, notes

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

app = FastAPI(title="ML SaaS Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

Base.metadata.create_all(bind=engine)

# ── Register all routers ──────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(data_catalog.router)
app.include_router(model_catalog.router)
app.include_router(preprocessing.router)
app.include_router(training.router)
app.include_router(notes.router)


# rendering of home.html page
@app.get("/")
def read_root(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("home.html", {"request": request})
    



def get_optional_user(request: Request, db: Session):
    try:
        user_id = get_current_user_id(request)
        if user_id:
            user = db.query(User).filter(User.user_id == int(user_id)).first()
            if user:
                return user.username
    except Exception:
        pass
    return None

@app.get("/about_developers")
def about_developers(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("about_developers.html", {"request": request, "username": get_optional_user(request, db)})

@app.get("/about_mission")
def about_mission(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("about_mission.html", {"request": request, "username": get_optional_user(request, db)})

@app.get("/about_techstack")
def about_techstack(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("about_techstack.html", {"request": request, "username": get_optional_user(request, db)})

@app.get("/about_guide")
def about_guide(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("about_guide.html", {"request": request, "username": get_optional_user(request, db)})

#websocket route for testing
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    #accept the websocket connection
    await websocket.accept()
    print("Client connected")
    while True:
        #receive the message from the client
        data = await websocket.receive_text()
        #send the message to the client
        await websocket.send_text(f"Message text was: {data}")
