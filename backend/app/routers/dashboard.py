from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import os

from app.db import get_db
from app.models import User
from app.security import get_current_user_id
from app.services.s3_operations import get_user_datasets, get_user_models

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

# rendering of the dashboard.html
@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    # checks if the user is logged in
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # checks if the user exists
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    datasets = get_user_datasets(db, int(user_id), limit=5)
    models = get_user_models(db, int(user_id), limit=5)

    print(f"DEBUG Dashboard: ID={user_id}, User={user.username}, Datasets={len(datasets)}, Models={len(models)}")

    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "username": user.username,
        "datasets": datasets,
        "models": models
    })