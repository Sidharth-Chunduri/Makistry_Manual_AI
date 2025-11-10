import datetime as dt, jwt, bcrypt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from app.core.config import settings
from app.services import storage  # ← your Firestore wrapper

bearer = HTTPBearer(auto_error=False)

def _sign(user_id: str, email: str, ttl_h: int = 24) -> str:
    payload = {"sub": user_id, "email": email,
               "exp": dt.datetime.utcnow() + dt.timedelta(hours=ttl_h)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

async def get_current_user(request: Request, cred = Depends(bearer)):
    if not cred:
        raise HTTPException(401, "Missing token")
    try:
        payload = jwt.decode(
            cred.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],   # ← list
            leeway=30,              # clock skew cushion
            options={"require": ["exp"]},
        )
        request.state.user_id = payload["sub"]
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
