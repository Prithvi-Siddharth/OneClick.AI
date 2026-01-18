from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.models import Base, User
from app.schemas import RegisterRequest, RegisterResponse
from app.security import hash_password, verify_password, create_access_token, get_current_user_id



#creates an app
app = FastAPI(title="ML SaaS Platform")

templates = Jinja2Templates(directory="app/templates")

#this command connects to the tidb and creates a table from the structure defined earlier
Base.metadata.create_all(bind=engine)

@app.get("/")
def read_root():
    return {"message": "Hello World"}


# Rendering of the register.html page
@app.get("/register")
def register_page(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("register.html", {"request": request})


# User registration endpoint
@app.post("/register")
async def register_user(
    request: Request,
    user_data: RegisterRequest = None,
    username: str = Form(default=None),
    email: str = Form(default=None),
    password: str = Form(default=None),
    db: Session = Depends(get_db),
):
    # Handle both JSON (API) and Form data (HTML form)
    if user_data:
        username = user_data.username
        email = user_data.email
        password = user_data.password
    
    # Validate required fields
    if not username or not email or not password:
        if request.headers.get("content-type") == "application/json":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All fields are required.",
            )
        else:
            return templates.TemplateResponse(
                "register.html",
                {
                    "request": request,
                    "error": "All fields are required.",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()

    if existing_user:
        if request.headers.get("content-type") == "application/json":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already exists.",
            )
        else:
            return templates.TemplateResponse(
                "register.html",
                {
                    "request": request,
                    "error": "Username or email already exists.",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    
    new_user = User(
        username=username,
        email=email,
        password=hash_password(password),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Return JSON for API calls, HTML response for form submissions
    if request.headers.get("content-type") == "application/json":
        return RegisterResponse(
            user_id=new_user.user_id,
            username=new_user.username,
            email=new_user.email,
            created_at=new_user.created_at,
        )
    else:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "message": "Registration successful! You can now log in.",
            },
            status_code=status.HTTP_201_CREATED,
        )


@app.get("/login")
def login_page(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login_user(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()

    if not user or not verify_password(password, user.password):
        return RedirectResponse(
            url="/login?error=invalid_credentials",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    access_token = create_access_token(
        data={"sub": str(user.user_id)}
    )

    response = RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,

    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,   # set True in production (HTTPS)
        samesite="lax",
    )

    return response

@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    return templates.TemplateResponse("dashboard.html", {"request": request, "username": user.username})

@app.get("/logout")
def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response