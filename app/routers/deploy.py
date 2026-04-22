from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from datetime import datetime

from app.db import get_db
from app.models import Experiment, User
from app.security import get_current_user_id

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))

# ── VIEW DEPLOY PAGE ─────────────────────────────────────────────────────────
@router.get("/deploy", response_class=HTMLResponse)
async def deploy_page(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login")

    user = db.query(User).filter(User.user_id == int(user_id)).first()
    
    # Fetch only completed (saved) models for this user
    user_models = db.query(Experiment).filter(
        Experiment.user_id == int(user_id),
        Experiment.status.in_(["COMPLETED", "DEPLOYED"])
    ).order_by(Experiment.id.desc()).all()

    return templates.TemplateResponse("deploy.html", {
        "request": request,
        "username": user.username if user else "User",
        "models": user_models
    })

# ── PROCESS DEPLOYMENT ────────────────────────────────────────────────────────
@router.post("/deploy_model")
async def process_deployment(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    data = await request.json()
    model_id = data.get("model_id")
    strategy = data.get("strategy", "api")

    # 1. Verify the model exists and belongs to the user
    model = db.query(Experiment).filter(
        Experiment.id == model_id, 
        Experiment.user_id == int(user_id)
    ).first()

    if not model:
        return JSONResponse(status_code=404, content={"error": "Model not found"})

    try:
        # 2. Simulate deployment logic (e.g., updating status/metadata)
        # In a real app, you might trigger a Docker build or a Kubernetes service here.
        model.status = "DEPLOYED" 
        db.commit()

        # 3. Return mock deployment details
        return JSONResponse(content={
            "status": "success",
            "message": f"Model '{model.name}' successfully deployed via {strategy.upper()}",
            "endpoint": f"https://api.oneclick.ai/v1/predict/{model.id}",
            "deployed_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
