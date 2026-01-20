from fastapi import FastAPI, Depends, HTTPException, status, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.models import Base, User, Dataset, Experiment
from app.schemas import RegisterRequest, RegisterResponse
from app.security import hash_password, verify_password, create_access_token, get_current_user_id
from app.services.s3_operations import get_user_datasets, get_user_models



#creates an app
app = FastAPI(title="ML SaaS Platform")

# directory of the templates
templates = Jinja2Templates(directory="app/templates")

#this command connects to the tidb and creates a table from the structure defined earlier
Base.metadata.create_all(bind=engine)

# rendering of home.html page
@app.get("/")
def read_root(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("home.html", {"request": request})
    

# Rendering of the register.html page
@app.get("/register")
def register_page(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("register.html", {"request": request})


# User registration endpoint
@app.post("/register")
async def register_user(
    request: Request, # raw request object, used to check content like headers and type 
    user_data: RegisterRequest = None, # the request input format given in schemas.py, pydantic schema for JSON input
    username: str = Form(default=None), # the username input field from the register.html page
    email: str = Form(default=None), # the email input field from register.html page
    password: str = Form(default=None), # the password input field from register.html page
    db: Session = Depends(get_db), # gives a db session to query and insert into db
):
    # Handle both JSON (API) and Form data (HTML form)
    if user_data:
        username = user_data.username
        email = user_data.email
        password = user_data.password
    
    # Validate required fields
    if not username or not email or not password: 
        if request.headers.get("content-type") == "application/json": # this is shown in the backend/ not in the UI
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All fields are required.",
            )
        else: # this is shown in the UI
            return templates.TemplateResponse(
                "register.html",
                {
                    "request": request,
                    "error": "All fields are required.", # this is variable to display in the UI, in register.html
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    
    # check if the username already exists
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()

    # if the username already exists, raise an error
    if existing_user:
        if request.headers.get("content-type") == "application/json":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already exists.",
            )
        else:
            # this is to display in the UI, in register.html
            return templates.TemplateResponse( 
                "register.html",
                {
                    "request": request,
                    "error": "Username or email already exists.",
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    
    # create a new user
    new_user = User(
        username=username,
        email=email,
        password=hash_password(password),
    )

    # add the new user to the database
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


# rendering of the login.html
@app.get("/login")
def login_page(request: Request, response_class=HTMLResponse):
    return templates.TemplateResponse("login.html", {"request": request})

# user login endpoint
@app.post("/login")
def login_user(
    # the email, password are taken from the form data
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):

    #checks if the user email already exists
    user = db.query(User).filter(User.email == email).first()

    # checks if the password is correct and modifies the variable error as query param here 
    if not user or not verify_password(password, user.password):
        return RedirectResponse(
            url="/login?error=invalid_credentials",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # access token is created
    access_token = create_access_token(
        data={"sub": str(user.user_id)}
    )

    # redirected to dashboard.html if the user is logged in successfully
    response = RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,

    )

    # the response cookie is set
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,   # set True in production (HTTPS)
        samesite="lax",
    )

    return response


# rendering of the dashboard.html
@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    # checks if the user is logged in
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # checks if the user exists
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    datasets = get_user_datasets(db, user.user_id)
    models = get_user_models(db, user.user_id)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "username": user.username,
        "datasets": datasets,
        "models": models
    })

@app.post("/upload_dataset")
def upload_dataset(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


# when the logout button is clicked, the access token cookie is deleted and redirected to login page
@app.get("/logout")
def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response