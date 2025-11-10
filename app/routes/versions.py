# app/routes/versions.py  (include in main.py or mount separately)

from fastapi import APIRouter, HTTPException, Query
from app.services import storage

router = APIRouter()

@router.get("/versions")
def list_versions(project_id: str):
    docs = storage.list_artifacts(project_id, art_type="version_bundle", latest=False)
    if not docs:                          # ⬅ always return a list
        return []

    # sort ascending by numeric version
    docs.sort(key=lambda d: int(d.get("version", 0)))
    return [
        {
            "version": int(d["version"]),
            "changed": d["data"]["changed"],
            "summary": d["data"]["summary"],
        }
        for d in docs
    ]

@router.get("/version")
def fetch_version(project_id: str, version: int = Query(...)):
    doc = storage.get_artifact(project_id, f"version_bundle_{version}")
    if not doc:
        raise HTTPException(404, f"Version {version} not found")
    return doc["data"]

@router.get("/latest-bundle")
def latest_bundle(project_id: str):
    docs = storage.list_artifacts(project_id, "version_bundle", latest=False)
    if not docs:
        return {"version": 1}
    return {"version": max(int(d["version"]) for d in docs)}