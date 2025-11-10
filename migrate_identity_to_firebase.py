# tools/migrate_identity_to_firebase.py
import firebase_admin
from firebase_admin import auth as fb_auth, credentials
from google.cloud import firestore

cred = credentials.Certificate("serviceAccount.json")
firebase_admin.initialize_app(cred)
fs = firestore.Client()

def run():
    for snap in fs.collection("identity").stream():
        d = snap.to_dict() or {}
        email = d.get("email")
        if not email: 
            continue
        if d.get("firebaseUid"):
            continue

        # ensure Firebase user exists
        try:
            u = fb_auth.get_user_by_email(email)
        except firebase_admin._auth_utils.UserNotFoundError:
            u = fb_auth.create_user(email=email)  # no password here

        # write UID to identity
        snap.reference.update({"firebaseUid": u.uid})

        # optional: send password reset link
        try:
            link = fb_auth.generate_password_reset_link(email)
            print(f"Password reset: {email} -> {link}")
            # You can email this link to the user via your mailer
        except Exception as e:
            print("Could not create reset link for", email, e)

if __name__ == "__main__":
    run()
