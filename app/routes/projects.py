# app/routes/projects.py
from fastapi import APIRouter, Depends, HTTPException
from google.cloud.firestore import Query as FSQuery
from app.services.auth import get_current_user
from app.services.storage_gcp import C_META
from google.cloud import firestore
from app.services import storage
from pydantic import BaseModel

router = APIRouter(prefix="/projects", tags=["projects"])

class VisibilityPatch(BaseModel):
    private: bool

@router.get("/tick")
def projects_tick(user=Depends(get_current_user)):
    """
    Returns a monotonic-ish number that bumps whenever any of the user's
    projects update. The client can compare this value when a user returns
    to the dashboard and refetch /projects only if it changed.
    """
    snaps = C_META.where("ownerID", "==", user["sub"]).select(["updatedAt"]).get()
    latest = 0
    for s in snaps:
        d = s.to_dict() or {}
        ts = d.get("updatedAt")
        if ts:
            try:
                # Firestore Timestamp -> epoch seconds (int)
                latest = max(latest, int(ts.timestamp()))
            except Exception:
                pass
    return {"latest": latest}

@router.get("")  # → handles GET /projects
def list_my_projects(user=Depends(get_current_user)):
    snaps = C_META.where("ownerID", "==", user["sub"]).get()
    rows = []
    for s in snaps:
        d = s.to_dict()
        rows.append({
            "id":        s.id,
            "title":     d.get("title", "Untitled"),
            "preview":   storage.get_signed_preview(d, s.id),
            "cadVersion": d.get("cadVersion"),
            "likes":     d.get("likesCount", 0),
            "remix":     d.get("remixCount", 0),
            "updatedAt": d.get("updatedAt"),  # sort with native Timestamp first
            "private":   bool(d.get("private", False)),
        })
    rows.sort(key=lambda r: (r["updatedAt"] or 0), reverse=True)
    # Final shape for the client:
    return [
        { **{k:v for k,v in r.items() if k!="updatedAt"},
          "updated": (r["updatedAt"].isoformat() if r["updatedAt"] else None) }
        for r in rows
    ]

from fastapi import Body

@router.patch("/{pid}/title")
def rename_project(pid: str, payload: dict, user=Depends(get_current_user)):
    title = payload.get("title", "").strip()
    if not title:
        raise Exception(400, "Title required")
    # update Firestore meta doc
    C_META.document(pid).update({
        "title": title,
        "updatedAt": firestore.SERVER_TIMESTAMP
    })
    return {"ok": True, "title": title}

@router.delete("/{pid}")
def delete_project(pid: str, user=Depends(get_current_user)):
    snap = C_META.document(pid).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Project not found")
    if snap.to_dict().get("ownerID") != user["sub"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    storage.delete_project(pid)
    return {"ok": True}

@router.patch("/{pid}/visibility")
def set_visibility(pid: str, data: VisibilityPatch, user=Depends(get_current_user)):
    snap = C_META.document(pid).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Project not found")
    meta = snap.to_dict() or {}
    if meta.get("ownerID") != user["sub"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    # only Pro can enable private projects
    features = storage.action_usage_snapshot(user["sub"]).get("features", {})
    is_allowed = bool(features.get("private_projects"))
    if data.private and not is_allowed:
        # 402 so the client can open an upgrade modal
        raise HTTPException(
            status_code=402,
            detail={"error": "feature_locked", "feature": "private_projects",
                    "message": "Upgrade to Pro to make private projects."}
        )

    C_META.document(pid).update({
        "private": bool(data.private),
        "updatedAt": firestore.SERVER_TIMESTAMP
    })
    return {"ok": True, "private": bool(data.private)}