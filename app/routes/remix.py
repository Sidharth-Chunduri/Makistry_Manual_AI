# app/routes/remix.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.services import storage
from app.services.storage_gcp import C_META, copy_blob, record_progress
from app.services.auth import get_current_user
from app.services.versioning import snapshot_bundle
from google.cloud import firestore
from pathlib import Path

router = APIRouter(prefix="/projects", tags=["projects"])

class RemixIn(BaseModel):
    stl_version: int
    brainstorm_version: int
    cad_code_version: int | None = None
    step_version: int | None = None


def _export_ext_from_doc(doc: dict) -> str:
    data = doc.get("data") or {}
    ext = (data.get("export") or "").lower()
    if ext == "stp":  # normalize
        return "step"
    return ext or "stl"


def _design_ver_from_doc(doc: dict) -> int | None:
    """
    Prefer explicit design_ver; else source_code_ver; else doc.version.
    This is the 'N' used in geometry/N.stl and geometry/N.step.
    """
    data = doc.get("data") or {}
    for key in ("design_ver", "source_code_ver", "version"):
        if data.get(key) is not None:
            try:
                return int(data.get(key))
            except Exception:
                pass
        if key == "version" and doc.get("version") is not None:
            try:
                return int(doc.get("version"))
            except Exception:
                pass
    return None


def _pick_stl_doc(src_id: str, preferred_ver: int | None):
    """
    Find an STL cad_file for the source. If preferred_ver provided,
    first try that exact version; next try the newest STL <= preferred;
    else the newest STL overall.
    """
    if preferred_ver is not None:
        doc = storage.get_artifact(src_id, f"cad_file_{int(preferred_ver)}_{src_id}")
        if doc and (_export_ext_from_doc(doc) == "stl"):
            return doc

    all_cad = storage.list_artifacts(src_id, "cad_file", latest=False) or []
    stls = [d for d in all_cad if _export_ext_from_doc(d) == "stl"]
    if not stls:
        return None
    if preferred_ver is not None:
        le = [d for d in stls if int(d.get("version", 0)) <= int(preferred_ver)]
        if le:
            return max(le, key=lambda d: int(d.get("version", 0)))
    return max(stls, key=lambda d: int(d.get("version", 0)))


def _pick_step_doc(src_id: str, preferred_design_ver: int | None):
    """
    Prefer a STEP whose design_ver/source_code_ver == preferred_design_ver.
    Else return newest STEP.
    """
    all_cad = storage.list_artifacts(src_id, "cad_file", latest=False) or []
    steps = [d for d in all_cad if _export_ext_from_doc(d) == "step"]
    if not steps:
        return None

    if preferred_design_ver is not None:
        matches = []
        for d in steps:
            dv = _design_ver_from_doc(d)
            try:
                if dv is not None and int(dv) == int(preferred_design_ver):
                    matches.append(d)
            except Exception:
                continue
        if matches:
            return max(matches, key=lambda d: int(d.get("version", 0)))

    return max(steps, key=lambda d: int(d.get("version", 0)))


def _clone_cad_file_from_doc(
    dst_project_id: str,
    user_id: str,
    session_id: str,
    src_doc: dict,
    *,
    # Back-compat alias (we'll treat force_ver like store_art_ver)
    force_ver: int | None = None,
    # The cad_file "version" stored in Firestore for the remix
    store_art_ver: int | None = None,
    # The filename slot used for geometry: cad-files/<pid>/geometry/<design_ver>.<ext>
    design_ver: int | None = None,
) -> int:
    """
    Copy a cad_file's blob (STL or STEP) into the remix project.

    store_art_ver: version number for the new cad_file artifact. If None, uses next_version().
    design_ver:    the 'N' used in geometry/N.stl or geometry/N.step. If None, uses store_art_ver.

    Returns the stored artifact version for the remix.
    """
    src_path = src_doc["data"]["gcs_path"]        # required on source
    ext = Path(src_path).suffix.lstrip(".").lower()
    if ext == "stp":
        ext = "step"

    art_ver = int(store_art_ver if store_art_ver is not None else (force_ver if force_ver is not None else storage.next_version(dst_project_id, "cad_file")))
    slot    = int(design_ver if design_ver is not None else art_ver)

    dst_path = f"cad-files/{dst_project_id}/geometry/{slot}.{ext}"

    copy_blob(src_path, dst_path)
    blob_url = storage.sign_path(dst_path)

    data_out = {**(src_doc.get("data") or {}), "gcs_path": dst_path, "design_ver": slot}

    storage.put_artifact(
        dst_project_id, user_id, session_id,
        art_type="cad_file",
        version=art_ver,
        blob_url=blob_url,
        data=data_out,
    )
    return art_ver


@router.post("/{src_id}/remix")
def remix_project(src_id: str, body: RemixIn, user=Depends(get_current_user)):
    uid = user["sub"]

    # ── 0) fetch source meta ───────────────────────────────────────
    snap = C_META.document(src_id).get()
    if not snap.exists:
        raise HTTPException(404, "Source project not found")
    src_meta = snap.to_dict() or {}

    # ── 1) create destination project ──────────────────────────────
    new_pid = storage.create_project(uid)
    base_name = src_meta.get("title", "Untitled")
    taken = {p.get("title") for p in storage.list_my_projects(uid)}
    idx = 1
    remix_name = f"{base_name}-{idx}"
    while remix_name in taken:
        idx += 1
        remix_name = f"{base_name}-{idx}"

    C_META.document(new_pid).set({
        "ownerID": uid,
        "title": remix_name,
        "origin": "remix",
        "originSrc": src_id,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    })

    # increment remixCount on the source
    C_META.document(src_id).update({"remixCount": firestore.Increment(1)})

    sess = f"remix_{new_pid}"

    # ── 2) clone artifacts aligned to the card preview ─────────────
    # Brainstorm
    b_id = f"brainstorm_{body.brainstorm_version}_{src_id}"
    b_doc = storage.get_artifact(src_id, b_id)
    if not b_doc:
        raise HTTPException(400, f"brainstorm version {body.brainstorm_version} not found")
    storage.put_artifact(
        new_pid, uid, sess,
        art_type="brainstorm", version=1,
        data=b_doc["data"],
    )

    # STL (required)
    stl_doc = _pick_stl_doc(src_id, int(body.stl_version))
    if not stl_doc:
        raise HTTPException(400, f"cad_file (STL) version {body.stl_version} not found")

    remix_design_ver = 1  # keep viewer deterministic: geometry/1.stl
    _clone_cad_file_from_doc(
        new_pid, uid, sess, stl_doc,
        store_art_ver=1,               # cad_file v1 in remix
        design_ver=remix_design_ver,   # geometry/1.stl
    )

    # CAD CODE (best-effort)
    code_doc = None
    if body.cad_code_version is not None:
        code_doc = storage.get_artifact(src_id, f"cad_code_{body.cad_code_version}_{src_id}")
    if not code_doc:
        code_doc = storage.get_artifact(src_id, f"cad_code_{body.stl_version}_{src_id}")
    if not code_doc:
        code_doc = storage.list_artifacts(src_id, "cad_code", latest=True) or None
    if code_doc:
        storage.put_artifact(
            new_pid, uid, sess,
            art_type="cad_code", version=1,
            data=code_doc["data"],
            parent_id=code_doc.get("id"),
        )

    # STEP (optional): prefer match to STL’s design version
    stl_design = _design_ver_from_doc(stl_doc) or int(stl_doc.get("version", 1))
    step_doc = None
    if body.step_version is not None:
        maybe = storage.get_artifact(src_id, f"cad_file_{body.step_version}_{src_id}")
        if maybe and _export_ext_from_doc(maybe) == "step":
            step_doc = maybe
    if step_doc is None:
        step_doc = _pick_step_doc(src_id, preferred_design_ver=stl_design)

    if step_doc:
        _clone_cad_file_from_doc(
            new_pid, uid, sess, step_doc,
            # artifact v2 in remix; but geometry stays at 1.step to match 1.stl
            store_art_ver=None,           # next cad_file version (→ 2)
            design_ver=remix_design_ver,  # geometry/1.step
        )

    # ── 3) snapshot bundle ────────────────────────────────────────
    snapshot_bundle(
        project_id=new_pid, user_id=uid, session_id=sess,
        changed=["Brainstorm", "Design"],
        summary=("Remix brainstorm and design added"),
    )

    # ── 4) set featured versions for UI ───────────────────────────
    C_META.document(new_pid).update({
        "brainVersion": 1,
        "cadVersion":   remix_design_ver,  # viewer signs geometry/{cadVersion}.stl
    })

    # ── 5) welcome message ────────────────────────────────────────
    storage.add_chat_message(
        new_pid, sess, uid,
        role="assistant",
        content=(
            "Great project to remix!\n"
            "I’ve copied the brainstorm and design into your workspace.\n"
            "Ask for changes in chat or generate new versions when you’re ready."
        ),
    )

    try:
        record_progress(uid, "remixes", unique_key=src_id)
    except Exception:
        pass

    return {"new_project_id": new_pid, "name": remix_name}
