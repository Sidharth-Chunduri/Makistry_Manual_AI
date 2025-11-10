from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, EmailStr
from app.services import storage
from app.services.auth import hash_pw, verify_pw, _sign

router = APIRouter(prefix="/auth", tags=["auth"])

class AuthIn(BaseModel):
    email: EmailStr
    password: str

@router.post("/signup")
def signup(data: AuthIn):
    if storage.identity_exists(data.email):
        raise HTTPException(409, "Email already in use")
    uid = storage.signup(data.email, data.password)   # helper you wrote
    token = _sign(uid, data.email)
    return {"token": token, "userId": uid}

@router.post("/login")
def login(data: AuthIn):
    token = storage.login(data.email, data.password)
    if not token:
        raise HTTPException(401, "Wrong email or password")
    return {"token": token}