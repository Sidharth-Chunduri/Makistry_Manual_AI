# app/routes/community.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.services import storage
from app.services.auth import get_current_user
from app.services.storage_gcp import C_META
import re

router = APIRouter(prefix="/community", tags=["community"])

class LikeIn(BaseModel):
    project_id: str

bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_user_optional(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict | None:
    """
    Return user dict when token is valid; otherwise None (never 401).
    """
    if not creds or not creds.credentials:
        return None
    try:
        # pass both arguments in the right order
        return await get_current_user(request, cred=creds)
    except HTTPException:
        return None


# ───────────────────────── helpers ─────────────────────────

_IMG_VER_RX = re.compile(r"/images/(\d+)\.(?:png|jpe?g|webp)\b", re.I)

def _preview_ver_from_url(url: str | None) -> int | None:
    if not url:
        return None
    m = _IMG_VER_RX.search(url.split("?", 1)[0])
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

def _is_stl_ver(pid: str, ver: int | None) -> bool:
    if ver is None:
        return False
    doc = storage.get_artifact(pid, f"cad_file_{int(ver)}_{pid}")
    return bool(doc and (doc.get("data") or {}).get("export") == "stl")

def _best_stl_for(pid: str, preferred: int | None) -> int | None:
    """
    Pick the STL version we should display:
    • If `preferred` is STL → keep it
    • Else → newest STL ≤ preferred
    • Else → newest STL overall
    """
    docs = storage.list_artifacts(pid, "cad_file", latest=False) or []
    stls = [d for d in docs if (d.get("data") or {}).get("export") == "stl"]
    if not stls:
        return None
    if preferred is not None:
        le = [d for d in stls if int(d.get("version", 0)) <= int(preferred)]
        if le:
            return int(max(le, key=lambda d: int(d.get("version", 0)))["version"])
    return int(max(stls, key=lambda d: int(d.get("version", 0)))["version"])

def _brain_for_cad_ver(pid: str, cad_ver: int | None) -> int | None:
    if cad_ver is None:
        return None
    bundles = storage.list_artifacts(pid, "version_bundle", latest=False) or []
    best = None
    for b in bundles:
        data = b.get("data") or {}
        try:
            if int(data.get("cad_file_ver", -1)) == int(cad_ver):
                if (best is None) or int(b.get("version", 0)) > int(best.get("version", 0)):
                    best = b
        except Exception:
            continue
    if best:
        bv = (best.get("data") or {}).get("brainstorm_ver")
        return int(bv) if bv is not None else None
    return None


# ───────────────────────── routes ─────────────────────────

@router.get("/feed")
async def community_feed(limit: int = 24, user=Depends(get_current_user_optional)):
    items = storage.get_community_feed(limit, sign_previews=True)
    uid = user["sub"] if user else None

    items = [it for it in items if it.get("preview")]

    # hydrate liked flags & ensure the CAD version we return is the one
    # that matches the card preview (and is an STL)
    for it in items:
        pid = it["id"]

        # 1) pick the version from the preview image url, if present
        #    (this is the version the user actually *sees* on the card)
        display_ver = _preview_ver_from_url(it.get("preview"))

        # 2) normalize to an STL version (newest STL ≤ display_ver; else newest STL)
        display_ver = _best_stl_for(pid, display_ver)

        # 3) fall back to legacy cadVersion if needed
        if display_ver is None:
            display_ver = _best_stl_for(pid, it.get("cadVersion"))

        it["cadVersion"] = display_ver

        # Map the brainstorm version that was current when this CAD was produced
        it["brainVersion"] = _brain_for_cad_ver(pid, display_ver)

        # liked flag
        it["likedByUser"] = bool(uid and storage.has_liked(pid, uid))

    # optional: hide my own originals
    if uid:
        items = [it for it in items if it.get("ownerID") != uid]

    # attach maker username + avatar
    owner_ids = [it.get("ownerID") for it in items if it.get("ownerID")]
    idmap = storage.fetch_identity_min(owner_ids)

    for it in items:
        ident = idmap.get(it.get("ownerID"), {})
        it["makerName"]  = ident.get("username") or "maker"
        it["makerPhoto"] = ident.get("photoUrl") or None
        it["makerTier"]  = ident.get("tier") or "apprentice"

    items.sort(
        key=lambda it: (
            int(it.get("likesCount", 0)),
            int(it.get("remixCount", 0)),
        ),
        reverse=True,
    )

    return items


@router.post("/like")
def like_route(data: LikeIn, user=Depends(get_current_user)):
    liked = storage.toggle_like(data.project_id, user["sub"])
    # read the authoritative count (single doc read)
    meta = C_META.document(data.project_id).get().to_dict() or {}
    likes_count = int(meta.get("likesCount", 0))
    return {"liked": liked, "likesCount": likes_count}

class ViewIn(BaseModel):
    project_id: str

@router.post("/view")
def view_route(data: ViewIn):
    storage.increment_view(data.project_id)
    return {"ok": True}
