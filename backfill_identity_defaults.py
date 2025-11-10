# scripts/backfill_identity_defaults.py
from app.services import storage_gcp as storage  # uses your existing clients
from google.cloud import firestore

import os, json
from app.core.config import settings
from app.services import storage_gcp as storage

print("settings.gcp_project =", settings.gcp_project)
print("firestore client project =", storage._fs.project)
sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
print("GOOGLE_APPLICATION_CREDENTIALS =", sa_path)
if sa_path and os.path.exists(sa_path):
    print("service account email =", json.load(open(sa_path))["client_email"])


def run(dry_run: bool = False):
    fs = storage._fs
    batch = fs.batch()
    changed = 0
    wrote = 0

    for s in storage.C_IDENTITY.stream():
        d = s.to_dict() or {}
        upd = {}

        if "username" not in d:
            email = d.get("email", "")
            upd["username"] = (email.split("@")[0] if email else f"user-{d.get('userID','')[:6]}")

        if "photoUrl" not in d:
            upd["photoUrl"] = None

        if "plan" not in d:
            upd["plan"] = "free"            # "free" | "pro"

        if "dailyQuota" not in d:
            upd["dailyQuota"] = 5

        if "creditsLeft" not in d:
            upd["creditsLeft"] = 5

        if "monthlyCredits" not in d:
            upd["monthlyCredits"] = 0

        if upd:
            changed += 1
            if dry_run:
                print(f"[DRY] would update {s.id}: {upd}")
            else:
                batch.set(s.reference, upd, merge=True)
                wrote += 1
                if wrote % 400 == 0:  # Firestore batch limit
                    batch.commit()
                    print(f"Committed {wrote} docs so far…")

    if not dry_run and wrote % 400:
        batch.commit()

    print(f"Scanned {changed if dry_run else wrote} docs. {'(dry-run)' if dry_run else '(written)'}")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print changes, don’t write")
    args = ap.parse_args()
    run(dry_run=args.dry_run)