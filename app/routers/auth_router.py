# app/routers/auth_router.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from ..schemas import token_schemas
from ..core import security
from ..db import crud, models # Import models ด้วยถ้าจะ Type Hint user
from ..db.database import get_db

router = APIRouter(
    tags=["Authentication"]
)

@router.post("/login", response_model=token_schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db_session: Session = Depends(get_db)
):
    user = crud.get_user_by_username(db_session, username=form_data.username) # <<--- ใช้ get_user_by_username

    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password", # เปลี่ยนข้อความ Error
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=security.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.username}, # <<--- Subject ของ Token คือ username
        expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}