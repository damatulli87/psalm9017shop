from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    return {"access_token": create_access_token(user.email), "token_type": "bearer"}


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    # Passwords travel in the JSON body, never in the URL/query string --
    # query params leak into server access logs and browser history.
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "ok"}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "role": user.role}
