from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from ..models import Note
from ..schemas import NoteCreate, NoteUpdate, NoteResponse
from ..security import get_current_user_id
from datetime import datetime

router = APIRouter(
    prefix="/notes",
    tags=["Notes"]
)

# Dependency to get current user ID
def get_user_id_or_401(request: Request) -> int:
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return int(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format in token")

@router.get("/", response_model=List[NoteResponse])
def get_notes(request: Request, db: Session = Depends(get_db)):
    """Fetch all sticky notes for the logged-in user."""
    user_id = get_user_id_or_401(request)
    notes = db.query(Note).filter(Note.user_id == user_id).all()
    return notes

@router.post("/", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(note_in: NoteCreate, request: Request, db: Session = Depends(get_db)):
    """Create a new sticky note."""
    user_id = get_user_id_or_401(request)
    new_note = Note(
        user_id=user_id,
        note_text=note_in.note_text,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note

@router.put("/{note_id}", response_model=NoteResponse)
def update_note(note_id: int, note_in: NoteUpdate, request: Request, db: Session = Depends(get_db)):
    """Update an existing sticky note."""
    user_id = get_user_id_or_401(request)
    note = db.query(Note).filter(Note.note_id == note_id, Note.user_id == user_id).first()
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    
    note.note_text = note_in.note_text
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return note

@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a sticky note."""
    user_id = get_user_id_or_401(request)
    note = db.query(Note).filter(Note.note_id == note_id, Note.user_id == user_id).first()
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    
    db.delete(note)
    db.commit()
    return None
