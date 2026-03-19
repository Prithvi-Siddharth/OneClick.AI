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

# -------- Sticky Notes Schemas --------
class NoteCreate(BaseModel):
    note_text: str

class NoteUpdate(BaseModel):
    note_text: str

class NoteResponse(BaseModel):
    note_id: int
    user_id: int
    note_text: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True