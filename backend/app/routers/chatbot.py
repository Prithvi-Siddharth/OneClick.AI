from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
import requests
import os

from app.db import get_db
from app.models import ChatUsage
from app.security import get_current_user_id

router = APIRouter()

EXTERNAL_CHAT_API = os.getenv("EXTERNAL_CHAT_API", "https://yexxsx2pz2.execute-api.us-east-1.amazonaws.com/prod/ask")


@router.post("/api/chat")
async def chat_proxy(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check current usage for today
    today = date.today()
    usage = db.query(ChatUsage).filter(
        ChatUsage.user_id == int(user_id),
        ChatUsage.chat_date >= datetime.combine(today, datetime.min.time()),
        ChatUsage.chat_date <= datetime.combine(today, datetime.max.time())
    ).first()

    if not usage:
        usage = ChatUsage(user_id=int(user_id), chat_date=datetime.utcnow(), usage_count=0)
        db.add(usage)
        db.commit()
        db.refresh(usage)
    
    if usage.usage_count >= 5:
        return JSONResponse(
            status_code=429,
            content={"error": "Daily chat limit reached (5/5). Please try again tomorrow!"}
        )
    
    # Increment usage
    usage.usage_count += 1
    db.commit()
    
    # Proxy the request to the external AI
    try:
        body = await request.json()
        query = body.get("query")
        if not query:
            return JSONResponse(status_code=400, content={"error": "No query provided"})
        
        response = requests.post(EXTERNAL_CHAT_API, json={"query": query}, timeout=30)
        response.raise_for_status()
        
        return response.json()
    except requests.exceptions.RequestException as e:
        # Rollback usage count if the external API fails (optional but fair)
        usage.usage_count -= 1
        db.commit()
        print(f"CHAT PROXY ERROR: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"EXTERNAL API RESPONSE: {e.response.text}")
        return JSONResponse(status_code=502, content={"error": f"AI Service currently unavailable: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
