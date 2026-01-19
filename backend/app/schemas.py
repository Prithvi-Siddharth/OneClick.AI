# Has all the request and response models (schemas) using Pydantic
from pydantic import BaseModel, EmailStr
from datetime import datetime

# model for user registration request
class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

# model for user registration response
class RegisterResponse(BaseModel):
    user_id: int
    username: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True