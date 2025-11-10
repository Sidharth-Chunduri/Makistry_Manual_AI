# app/api/v1/auth_firebase.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import firebase_admin
from firebase_admin import auth as fb_auth, credentials
from google.cloud import firestore
from app.services import storage          # your Firestore wrapper
from app.services.auth import _sign       # Makistry JWT
from datetime import datetime
from app.services.auth import get_current_user

# Initialize Firebase Admin SDK with service account
try:
    firebase_admin.get_app()
    print("[DEBUG] Firebase Admin SDK already initialized")
except ValueError:
    # Use the service account file from our config
    import os
    service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if service_account_path and os.path.exists(service_account_path):
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        print(f"[DEBUG] Firebase Admin SDK initialized with service account: {service_account_path}")
    else:
        print(f"[DEBUG] Service account path not found: {service_account_path}")
        firebase_admin.initialize_app(credentials.ApplicationDefault())
        print("[DEBUG] Firebase Admin SDK initialized with Application Default Credentials")

router = APIRouter(prefix="/auth", tags=["auth"])

class IdTokenIn(BaseModel):
    idToken: str

@router.post("/firebase")
def firebase_login(data: IdTokenIn):
    # 1) Verify signature & expiry
    try:
        print(f"[DEBUG] Attempting to verify Firebase ID token...")
        decoded = fb_auth.verify_id_token(data.idToken)
        print(f"[DEBUG] Firebase ID token verified successfully for: {decoded.get('email', 'unknown')}")
    except Exception as e:
        print(f"[DEBUG] Firebase ID token verification failed: {e}")
        raise HTTPException(401, "Bad Firebase token")

    email        = decoded["email"].lower()
    firebase_uid = decoded["uid"]
    print(f"[DEBUG] Processing login for email: {email}, uid: {firebase_uid}")

    # 2) Temporary workaround: Skip Firestore operations due to DNS issues
    # Just create a simple user_id for now
    user_id = f"user_{firebase_uid[:8]}"
    print(f"[DEBUG] Using temporary user_id: {user_id} (Firestore connection issues)")

    # 3) Return Makistry-scoped JWT (unchanged everywhere else)
    print(f"[DEBUG] Generating JWT for user: {user_id}")
    token = _sign(user_id, email)
    print(f"[DEBUG] Successfully generated JWT")
    return {"token": token, "userId": user_id}

@router.post("/firebase_custom")
def create_firebase_custom_token(current_user: dict = Depends(get_current_user)):
    try:
        user_id = current_user["sub"]
        email = current_user["email"]

        doc_ref = storage.C_IDENTITY.document(email.lower())
        snap = doc_ref.get()
        if not snap.exists:
            raise HTTPException(404, "User identity not found")

        identity_data = snap.to_dict()
        firebase_uid = identity_data.get("firebaseUid")
        if not firebase_uid:
            raise HTTPException(400, "No Firebase UID found for user")

        # ✅ Python Admin SDK: use `developer_claims`
        custom_token = fb_auth.create_custom_token(
            firebase_uid,
            developer_claims={
                "makistry_user_id": user_id,   # keep small & non-reserved
                # avoid putting "email" here; see note below
            }
        )

        return { "customToken": custom_token.decode("utf-8"), "uid": firebase_uid }

    except Exception as e:
        print(f"Error creating custom token: {e}")
        raise HTTPException(500, f"Failed to create custom token: {str(e)}")