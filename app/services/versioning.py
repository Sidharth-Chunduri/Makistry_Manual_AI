# app/services/versioning.py
from __future__ import annotations
from typing import List
from app.services import storage

_ART_TYPE = "version_bundle"          # keep it in one place


def _latest(art_type: str, project_id: str):
    doc = storage.list_artifacts(project_id, art_type, latest=True)
    return doc.get("version") if doc else None


def next_version(project_id: str) -> int:
    """Next bundle number (1-based)."""
    items = storage.list_artifacts(project_id, _ART_TYPE, latest=False)
    return 1 if not items else max(int(x["version"]) for x in items) + 1


def snapshot_bundle(
    *,
    project_id: str,
    user_id: str,
    session_id: str,
    changed: List[str],       # e.g. ["brainstorm"] or ["design"]
    summary: str,
) -> None:
    """Capture *current* versions of all artefact types into one record."""
    data = {
        "brainstorm_ver": _latest("brainstorm",  project_id),
        "cad_code_ver":   _latest("cad_code",    project_id),
        "cad_file_ver":   _latest("cad_file",    project_id),
        "changed":        changed,               # for the UI chip
        "summary":        summary,               # one-liner shown on card
    }
    storage.put_artifact(
        project_id, user_id, session_id,
        art_type=_ART_TYPE,
        version=next_version(project_id),
        data=data,
    )
