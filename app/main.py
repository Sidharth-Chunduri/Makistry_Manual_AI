# app/main.py
from __future__ import annotations
import json, pathlib, uuid, time, re
from typing import Optional
import logging
from pathlib import Path
import traceback
import sys
# import jinja2
from io import BytesIO
from PIL import Image
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import os
import reportlab
import asyncio
import threading

from fastapi import FastAPI, HTTPException, BackgroundTasks, Body, Query, Depends
from pydantic import BaseModel, Field
from traceback import format_exc
from fastapi.middleware.cors import CORSMiddleware
from operator import itemgetter
from fastapi.responses import StreamingResponse, RedirectResponse
from app.services.storage import last_chat_messages, download_blob_to_temp
from app.routes.share import share_preview_html

from app.agents.brainstorm      import heavy_brainstorm
# from app.agents.code_creation_azure   import generate_cadquery
from app.agents.code_creation_aws   import generate_cadquery
from app.services.feature_tree_sync import feature_tree_sync
from app.agents.code_edit       import fix_cadquery, edit_cadquery
from app.services.cad_generation_integration import cad_integration
from app.services.sandbox       import run_cadquery, SandboxError
from app.agents.brainstorm_edit import edit_brainstorm
from app.services               import storage
from app.agents.intent_classifier import classify_intents
from app.agents.chat_agent import stream_reply
from app.services.versioning import snapshot_bundle
from app.agents.planner import make_plan
from fastapi import Depends, Request
from app.services.auth import get_current_user
from app.routes.helpers import artifact_id
from app.routes import community 
from app.routes import thumbnails
from app.routes import auth as auth_routes
from app.routes import chat_history, projects
from app.routes import remix 
from app.routes import share
from app.core.config import settings
from app.agents.preflight import quick_preflight
from app.api.v1.auth_firebase import router as auth_firebase_router
from app.routes import feature_tree
from app.routes import account
from google.cloud import firestore
from app.services.storage_gcp import C_META
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import app.api.v1.auth_magic as magic_router
from app.routes import billing
from openai import APIStatusError

app = FastAPI(title="Makistry MVP")
SESSION_ID = lambda: f"sess_{uuid.uuid4().hex[:6]}"
TIMESTAMP  = lambda: int(time.time() * 1000)
BASE = Path(__file__).parent
# TEMPLATE = jinja2.Template((BASE / "templates" / "brainstorm.html").read_text())
bearer_scheme = HTTPBearer(auto_error=False)

app.include_router(community.router,  prefix="/api")
app.include_router(account.router,    prefix="/api")
app.include_router(projects.router,   prefix="/api")
app.include_router(chat_history.router, prefix="/api")
app.include_router(thumbnails.router, prefix="/api")
app.include_router(remix.router,      prefix="/api")
app.include_router(share.router,      prefix="/api")
app.include_router(share.router,      include_in_schema=False)
app.include_router(auth_firebase_router, prefix="/api")
app.include_router(feature_tree.router, prefix="/api")
app.include_router(billing.router, prefix="/api")

try:
    import app.api.v1.auth_magic as magic_router
    app.include_router(magic_router.router, prefix="/api")
except Exception as e:
    print(f"[Makistry] Skipping auth_magic at startup: {e}", file=sys.stderr)

static_path = Path(__file__).parent / "static" / "build"  # Adjust path as needed
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# --- Project-level lock for /generate-design ---------------------------------
LOCK_TTL_S = int(os.getenv("CODEGEN_LOCK_TTL_S", "900"))  # 15 min default

def _now_ms() -> int:
    return int(time.time() * 1000)

def _acquire_codegen_lock(project_id: str, user_id: str, session_id: str, ttl_s: int = LOCK_TTL_S):
    """Returns (acquired: bool, info: dict). Uses Firestore transaction on C_META/{project_id}."""
    doc = C_META.document(project_id)
    tx = firestore.Client().transaction()

    @firestore.transactional
    def _do(t):
        snap = doc.get(transaction=t)
        data = snap.to_dict() or {}
        locks = data.get("locks") or {}
        lock  = locks.get("codegen")
        now   = _now_ms()

        # respect unexpired lock
        if lock and int(lock.get("expiresAt", 0)) > now:
            return False, lock

        new_lock = {
            "owner": user_id,
            "session": session_id,
            "startedAt": now,
            "expiresAt": now + ttl_s * 1000,
        }
        locks["codegen"] = new_lock
        t.set(doc, {"locks": locks, "cadGenerating": True}, merge=True)
        return True, new_lock

    return _do(tx)

def _release_codegen_lock(project_id: str, session_id: str | None, force: bool = False):
    """Releases the codegen lock if owned or if force=True. Returns True/False."""
    doc = C_META.document(project_id)
    tx = firestore.Client().transaction()

    @firestore.transactional
    def _do(t):
        snap = doc.get(transaction=t)
        data = snap.to_dict() or {}
        locks = data.get("locks") or {}
        lock  = locks.get("codegen")

        if not lock:
            t.set(doc, {"cadGenerating": False}, merge=True)
            return True

        if not force and session_id and lock.get("session") != session_id:
            # someone else's lock → do not release
            return False

        locks.pop("codegen", None)
        t.set(doc, {"locks": locks, "cadGenerating": False}, merge=True)
        return True

    return _do(tx)

@app.get("/project-state")
def project_state(project_id: str):
    try:
        meta = C_META.document(project_id).get().to_dict() or {}
    except Exception:
        meta = {}
    return {
        "cadGenerating": bool(meta.get("cadGenerating")),
        "lock": (meta.get("locks") or {}).get("codegen"),
        "cadVersion": meta.get("cadVersion"),
    }

@app.get("/api/project-state")
def _api_project_state(project_id: str = Query(...)):
    return project_state(project_id)

@app.get("/api/healthz")
def healthz():
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "service": "makistry"}

UI_ORIGIN = os.getenv("UI_ORIGIN", "")
_origins = ["http://localhost:8080", "http://localhost:5173", "https://makistry.ai", "https://www.makistry.ai"]
if UI_ORIGIN and UI_ORIGIN != "*":
    _origins.append(UI_ORIGIN)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────── Request models ───────────────────────────
class BrainstormIn(BaseModel):
    prompt: str

class DesignIn(BaseModel):
    project_id: Optional[str] = None
    brainstorm: Optional[dict] = None
    file_path: Optional[str] = None

    @property
    def has_payload(self):
        return bool(self.brainstorm) or bool(self.file_path)

class CadEditIn(BaseModel):
    project_id: str
    user_query: str 
    cad_code_version: int | None = None

class BrainstormEditIn(BaseModel):
    project_id: str
    user_query: str
    brainstorm_version: int | None = None

class StepExportIn(BaseModel):
    project_id: str
    cad_code_version: int | None = None

def latest_artifact(project_id: str, art_type: str):
    arts = storage.list_artifacts(project_id=project_id, art_type=art_type, latest=False)
    if not arts:
        return None
    def to_int(v):
        try:
            return int(v)
        except Exception:
            s = str(v)
            num = ""
            for ch in s:
                if ch.isdigit():
                    num += ch
                else:
                    break
            return int(num) if num else 0
    return max(arts, key=lambda d: to_int(d.get("version", 0)))

def latest_cad_code(project_id: str) -> str | None:
    doc = latest_artifact(project_id, "cad_code")
    if not doc:
        return None
    return doc["data"]["code"]

# main.py (near latest_artifact)
def get_artifact_for_version(project_id: str, art_type: str, version: int | None):
    if version is not None:
        art_id = artifact_id(art_type, version, project_id)
        return storage.get_artifact(project_id, art_id)
    return latest_artifact(project_id, art_type)

async def optional_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    try:
        if not creds or not creds.credentials:
            return None
        return await get_current_user(request, cred=creds)
    except HTTPException:
        return None


class ClassifierIn(BaseModel):
    project_id: str
    user_query: str

class ChatIn(BaseModel):
    project_id: str
    user_query: str
    cad_code_version: int | None = None
    brainstorm_version: int | None = None

# --- background STEP exporter (no Depends here) ---
def _export_step_bg(
    project_id: str,
    session_id: str,
    user_id: str,
    code: str,
    code_ver: int,
    *,
    award_on_complete: bool = False,
) -> None:
    """Background task to export STEP file with improved error handling"""
    try:
        logger.info(f"Starting STEP export for project {project_id}, version {code_ver}")
        
        # Run CadQuery to generate STEP file
        step_path = run_cadquery(code, ext="stp")
        logger.info(f"Generated STEP file at: {step_path}")

        # Upload to storage (prefer gz upload if available)
        try:
            url, gcs_path = storage.upload_step_gz(step_path, project_id, code_ver, ttl_sec=86_400)
            logger.info(f"Uploaded STEP (gz) to: {gcs_path}")
        except AttributeError:
            # Fallback to regular geometry upload
            url, gcs_path = storage.upload_geometry(step_path, project_id, code_ver, "step", ttl_sec=86_400)
            logger.info(f"Uploaded STEP to: {gcs_path}")

        # Store artifact record
        step_version = storage.next_version(project_id, "cad_file")
        storage.put_artifact(
            project_id, user_id, session_id,
            art_type="cad_file",
            version=step_version,
            blob_url=url,
            data={
                "export": "step",
                "filename": Path(step_path).name,
                "gcs_path": gcs_path,
                "source_code_ver": int(code_ver),
                "design_ver": int(code_ver),
            },
        )
        logger.info(f"Stored STEP artifact with version {step_version}")

        # Award progress if requested
        if award_on_complete:
            try:
                storage.record_progress(
                    user_id, "exports",
                    unique_key=f"{project_id}:step:{int(code_ver)}"
                )
                logger.info(f"Awarded progress for STEP export")
            except Exception as e:
                logger.error(f"Failed to award progress: {e}")

        # Log successful operation
        storage.log_operation(
            user_id, project_id, session_id,
            op_type="sandbox", agent="cadquery",
            tokens_prompt=0, tokens_comp=0, latency_ms=0,
            status="success"
        )
        logger.info(f"STEP export completed successfully for project {project_id}")

    except Exception as exc:
        logger.error(f"STEP export failed for project {project_id}: {exc}")
        logger.error(f"Full traceback: {format_exc()}")
        
        # Log failed operation
        storage.log_operation(
            user_id, project_id, session_id,
            op_type="sandbox", agent="cadquery",
            tokens_prompt=0, tokens_comp=0, latency_ms=0,
            status="error", error=str(exc)
        )
    finally:
        # Always release the lock
        try:
            _release_step_lock(project_id, code_ver)
            logger.info(f"Released STEP lock for project {project_id}, version {code_ver}")
        except Exception as e:
            logger.error(f"Failed to release STEP lock: {e}")


def _enforce_ai_quota_or_402(user_id: str):
    allowed, info = storage.check_ai_allowed(user_id)
    if not allowed:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "credit_limit_reached",
                "message": "You’ve hit your daily or monthly credit limit.",
                "limits": {
                    "dailyQuota": info["dailyQuota"],
                    "creditsLeft": info["creditsLeft"],
                    "creditsToday": info["creditsToday"],
                    "monthlyCap": info["monthlyCap"],
                    "monthlyUsed": info["monthlyUsed"],
                    "monthlyRemaining": info["monthlyRemaining"],
                    "dayResetAtISO": info["dayResetAtISO"],
                    "monthResetAtISO": info["monthResetAtISO"],
                },
            },
        )
    
def _enforce_action_or_402(user_id: str, action: str):
    allowed, info = storage.check_action_allowed(user_id, action)
    if allowed:
        return
    if action in ("export_stl", "export_step"):
        kind = "stl" if action.endswith("stl") else "step"
        mon = info["month"][kind]
        raise HTTPException(
            status_code=402,
            detail={
                "error": "limit_reached_action",
                "action": f"export_{kind}",
                "message": f"You’ve reached your monthly {kind.upper()} export limit.",
                "limits": {"used": mon["used"], "cap": mon["cap"], "resetAtISO": mon["resetAtISO"]},
            },
        )
    if action == "project_create":
        wk = info["week"]["projects"]
        raise HTTPException(
            status_code=402,
            detail={
                "error": "limit_reached_action",
                "action": "project_create",
                "message": "You’ve reached your weekly new-project limit.",
                "limits": {"used": wk["used"], "cap": wk["cap"], "resetAtISO": wk["resetAtISO"]},
            },
        )


# ──────────────────────────── Brainstorm  ───────────────────────────────
@app.post("/brainstorm")
def brainstorm_route(data: BrainstormIn, user=Depends(get_current_user)):
    USER_ID = user["sub"]
    _enforce_ai_quota_or_402(USER_ID) 
    _enforce_action_or_402(USER_ID, "project_create")
    proj_id = storage.create_project(USER_ID)
    try:
        storage.consume_action(USER_ID, "project_create")  # ← NEW
    except Exception:
        pass
    session   = SESSION_ID()
    t0        = TIMESTAMP()
    
    try:
        brainstorm, usage = heavy_brainstorm(data.prompt)
    except APIStatusError as exc:
        detail = "Azure OpenAI returned an error"
        try:
            body = exc.response.json()
            detail = (
                body.get("error", {}).get("message")
                or body.get("error")
                or str(exc)
            )
        except Exception:
            detail = str(exc) or detail
        raise HTTPException(502, detail=f"Azure OpenAI error: {detail}")
    except RuntimeError as e:
        # failed to parse JSON, send back the raw text so the UI can render
        raw = str(e).split("Invalid JSON from model:\n", 1)[-1]
        return {"project_id": proj_id, "brainstorm": {"_raw": raw}}
    except Exception as exc:
        logging.exception("Brainstorm generation failed")
        raise HTTPException(502, detail="Brainstorm generation failed")

    latency = TIMESTAMP() - t0

    storage.put_artifact(
        proj_id, USER_ID, session,
        art_type="brainstorm", version=1, data=brainstorm
    )
    storage.log_operation(
        USER_ID, proj_id, session,
        op_type="brainstorm", agent="gpt-4.1",
        tokens_prompt=usage.prompt_tokens, tokens_comp=usage.completion_tokens, latency_ms=latency
    )
    storage.add_chat_message(
        proj_id, session, USER_ID, role="user", content=data.prompt
    )
    message_lines = [
        "That sounds like a great project!",
        "I've brainstormed a few ideas to get us started.",
        "You can ask me questions or request changes to any part of the brainstorm in the chat.",
        "Click the 'Generate Design' button to create a 3D CAD model using the brainstorm when you're ready!"
    ]
    message = "\n".join(message_lines)
    storage.add_chat_message(
        proj_id, session, USER_ID, role="assistant", content=message
    )
    snapshot_bundle(
        project_id=proj_id,
        user_id=USER_ID,
        session_id=session,
        changed=["Brainstorm"],
        summary="Initial Brainstorm created",
    )
    storage.upsert_project_meta(
        project_id=proj_id,
        owner_id=USER_ID,
        title=brainstorm.get("project_name") or "Untitled project",
        brainVersion=1,
    )

    return {"project_id": proj_id, "brainstorm": brainstorm}

# ──────────────────────────── Generate CAD  ─────────────────────────────
# ──────────────────────────── Generate CAD  ─────────────────────────────
MAX_RETRIES = 5
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.post("/generate-design")
def generate_design_route(data: DesignIn, tasks: BackgroundTasks, user=Depends(get_current_user)):
    """
    New async-friendly implementation:
    - Generates CAD code synchronously and stores it
    - Schedules STL generation/upload/meta updates as a BackgroundTask via _sandbox_flow
    - Returns quickly so edge/proxy timeouts are never hit
    - The UI polls /latest-cad (already implemented) until STL is ready
    """
    scheduled = False
    try:
        if not data.project_id and not data.has_payload:
            raise HTTPException(422, "Provide project_id or brainstorm payload")

        USER_ID = user["sub"]
        _enforce_ai_quota_or_402(USER_ID)

        # Create or reuse project
        if not data.project_id:
            _enforce_action_or_402(USER_ID, "project_create")
            proj_id = storage.create_project(USER_ID)
            try:
                storage.consume_action(USER_ID, "project_create")
            except Exception:
                pass
        else:
            proj_id = data.project_id

        session = SESSION_ID()

        acquired, lock = _acquire_codegen_lock(proj_id, USER_ID, session)
        if not acquired:
            # Someone else is generating for this project
            raise HTTPException(
                status_code=409,
                detail={"error": "in_progress", "lock": lock}
            )

        # Fetch brainstorm JSON
        if data.has_payload:
            brainstorm = (
                data.brainstorm
                if data.brainstorm
                else json.loads(pathlib.Path(data.file_path).read_text())
            )
            if not brainstorm or "key_features" not in brainstorm:
                raise HTTPException(400, "No valid brainstorm found for this project")
        else:
            doc = latest_artifact(proj_id, "brainstorm")
            if not doc:
                raise HTTPException(404, "Brainstorm not found in storage")
            brainstorm = doc["data"]

        # Generate CAD code with Bedrock and create feature tree
        t0 = TIMESTAMP()
        try:
            cad_code, feature_tree, usage = cad_integration.generate_cad_with_feature_tree(
                brainstorm, proj_id, USER_ID, session
            )
        except Exception as exc:
            # Log failed attempt and bubble up
            latency = TIMESTAMP() - t0
            storage.log_operation(
                USER_ID, proj_id, session,
                op_type="code_creation",
                agent="o4-mini",
                tokens_prompt=0, tokens_comp=0,
                latency_ms=latency,
                status="error", error=str(exc)
            )
            raise HTTPException(500, f"Code-generation error: {exc}") from exc

        latency = TIMESTAMP() - t0

        # Persist CAD code artifact
        ver = storage.next_version(proj_id, "cad_code")
        storage.put_artifact(
            proj_id, USER_ID, session,
            art_type="cad_code", version=ver, data={
                "code": cad_code,
                "feature_tree_id": feature_tree.id,
                "feature_tree_version": feature_tree.version,
                "node_count": len(feature_tree.nodes)
            }
        )
        storage.log_operation(
            USER_ID, proj_id, session,
            op_type="code_creation", agent="sonnet-4",
            tokens_prompt=usage.get("input_tokens", 0),
            tokens_comp=usage.get("output_tokens", 0),
            latency_ms=latency
        )
        
        # Create initial version bundle with CAD code immediately
        # This ensures frontend can see there's design content available
        try:
            snapshot_bundle(
                project_id=proj_id,
                user_id=USER_ID,
                session_id=session,
                changed=["Design"],
                summary="Initial CAD code generated"
            )
            logger.info(f"[generate_design] Created initial version bundle for project {proj_id}")
        except Exception as e:
            logger.warning(f"[generate_design] Failed to create initial version bundle: {e}")

        # IMPORTANT:
        # Do NOT set cadVersion or send "ready" chat here.
        # Schedule background STL workflow; it will:
        #  - run CadQuery (with retries/fixes)
        #  - upload STL + write cad_file artifact
        #  - send "Your CAD model is ready!" chat message
        #  - set projects_meta.cadVersion
        #  - kick off STEP export
        tasks.add_task(
            _sandbox_flow,
            proj_id,
            session,    # session_id
            USER_ID,
            cad_code,
            ver,
            "stl",
            True,
        )
        scheduled = True

        # Assistant message (identical text as before)
        message_lines_cad = [
            "Your CAD model is ready!",
            "Now you can:",
            "• View and interact with the 3D model.",
            "• Ask questions or request changes to the design and brainstorm in the chat.",
            "• Toggle between the brainstorm and design tabs.",
            "Share or export your design when you're ready.",
        ]
        storage.add_chat_message(
            proj_id, session, USER_ID,
            role="assistant", content="\n".join(message_lines_cad)
        )

        # Snapshot bundle (Design changed) right away so history looks responsive
        try:
            snapshot_bundle(
                project_id=proj_id,
                user_id=USER_ID,
                session_id=session,
                changed=["Design"],
                summary="Initial Design created",
            )
        except Exception:
            pass

        # Return quickly: UI will poll /latest-cad; do not return blob_url here
        return {
            "project_id": proj_id,
            "cad_version": ver,
            # "blob_url": omitted on purpose (becomes available via /latest-cad)
        }

    except HTTPException:
        raise
    except Exception as uncaught:
        logger.error("UNHANDLED in /generate-design:\n%s", format_exc())
        raise HTTPException(500, f"Internal error: {uncaught}")
    finally:
        # Only release if background task was NOT scheduled (i.e., we failed early)
        if not scheduled:
            try:
                _release_codegen_lock(proj_id, session_id=session)
            except Exception:
                pass

    
@app.get("/latest-brainstorm")
def latest_brainstorm(project_id: str = Query(..., description="Project to check"), version: int | None = Query(None)):
    if version:
        art_id = artifact_id("brainstorm", version, project_id)
        doc = storage.get_artifact(project_id, art_id)
        if not doc:
            raise HTTPException(404, "Version not found")
    else:
        doc = storage.list_artifacts(project_id=project_id, art_type="brainstorm", latest=True)
    if not doc:
        return {"status": "pending"}
    
    return {
        "status": "ready",
        "brainstorm": doc["data"],
        "version": doc["version"],
    }

async def _wait_for_stl_ready(project_id: str, version: int, timeout_s: int = 120) -> bool:
    for _ in range(timeout_s):
        try:
            if storage.stl_exists(project_id, version):
                return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False

# ------------------------------------------------------------------
#  Internal: run CadQuery + upload STL + store artefact
#  (replicates the exact sync logic from /generate-design)
# ------------------------------------------------------------------
def _sandbox_flow(
    project_id: str,
    session_id: str,
    user_id: str,
    code: str,
    code_ver: int,
    export: str = "stl",
    add_message: bool = True,
) -> None:
    """
    Background STL pipeline (unchanged behavior, moved off-thread):
    - Runs CadQuery with retries and fix_cadquery()
    - Uploads STL and writes cad_file artifact
    - Posts "ready" assistant message
    - Sets projects_meta.cadVersion (authoritative viewer slot)
    - Starts STEP export
    - ALWAYS releases the codegen lock at the end
    """
    export = export.lower()

    try:
        # --- retry loop for sandbox run (same logic you had) ---
        file_path: str | None = None
        last_error: str | None = None
        for attempt in range(MAX_RETRIES):
            try:
                file_path = run_cadquery(code)
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
                try:
                    code, usage1 = fix_cadquery(code, last_error)
                    tokens_prompt = getattr(usage1, "prompt_tokens", 0)
                    tokens_comp   = getattr(usage1, "completion_tokens", 0)
                    if isinstance(usage1, dict):
                        tokens_prompt = usage1.get("prompt_tokens", 0)
                        tokens_comp   = usage1.get("completion_tokens", 0)
                    storage.log_operation(
                        user_id, project_id, session_id,
                        op_type="code_fix", agent="o4-mini",
                        tokens_prompt=tokens_prompt, tokens_comp=tokens_comp, latency_ms=0
                    )
                except Exception:
                    # Keep retrying even if fix step fails once
                    pass

        if not file_path:
            logger.error("Initial sandbox failed after retries:\n%s", format_exc())
            storage.log_operation(
                user_id, project_id, session_id,
                op_type="sandbox", agent="cadquery",
                tokens_prompt=0, tokens_comp=0, latency_ms=0,
                status="error", error=f"Initial sandbox failed: {last_error}"
            )
            return

        # --- upload STL + cad_file artifact ---
        blob_url, gcs_path = storage.upload_geometry(
            file_path, project_id, code_ver, "stl", ttl_sec=86_400
        )
        try:
            slot_path = storage.geometry_blob_path(project_id, code_ver, "stl")
            exists = storage.stl_exists(project_id, code_ver)
            logger.info(
                f"[sandbox_flow] STL uploaded: slot_exists={exists} "
                f"slot_path={slot_path} gcs_path={gcs_path}"
            )
        except Exception as ee:
            logger.warning(f"[sandbox_flow] stl_exists check failed: {ee}")

        storage.put_artifact(
            project_id, user_id, session_id,
            art_type="cad_file", version=f"{code_ver}",
            blob_url=blob_url,
            data={
                "export": export,
                "filename": Path(file_path).name,
                "gcs_path": gcs_path,
                "design_ver": int(code_ver),
            },
        )

        # Update meta so /latest-cad can find the authoritative viewer slot
        logger.info(f"[sandbox_flow] About to update project meta for project {project_id}")
        try:
            doc = latest_artifact(project_id, "brainstorm")
            title = (doc["data"].get("project_name") if doc else None) or "Untitled project"
        except Exception:
            title = "Untitled project"
        try:
            storage.upsert_project_meta(
                project_id=project_id,
                owner_id=user_id,
                title=title,
                cadVersion=code_ver,
            )
            logger.info(f"[sandbox_flow] Successfully updated project meta for project {project_id}")
        except Exception as e:
            logger.warning(f"[sandbox_flow] Failed to update project meta: {e}")

        logger.info(f"[sandbox_flow] About to start STEP export thread for project {project_id}")
        try:
            threading.Thread(
                target=_export_step_bg,
                args=(project_id, session_id, user_id, code, code_ver),
                kwargs={"award_on_complete": False},
                daemon=True,
            ).start()
            logger.info(f"[sandbox_flow] Successfully started STEP export thread for project {project_id}")
        except Exception as e:
            logger.warning(f"[sandbox_flow] Failed to start STEP export thread: {e}")

        # Log success for the sandbox op
        logger.info(f"[sandbox_flow] About to log sandbox operation success for project {project_id}")
        storage.log_operation(
            user_id, project_id, session_id,
            op_type="sandbox", agent="cadquery",
            tokens_prompt=0, tokens_comp=0, latency_ms=0,
            status="success"
        )
        logger.info(f"[sandbox_flow] Successfully logged sandbox operation for project {project_id}")

        # Create version bundle snapshot to include the new cad_file_ver
        # This ensures /versions endpoint returns the correct cad_file_ver for frontend
        logger.info(f"[sandbox_flow] About to create version bundle snapshot for project {project_id}")
        try:
            snapshot_bundle(
                project_id=project_id,
                user_id=user_id,
                session_id=session_id,
                changed=["Design"],
                summary="CAD model generated"
            )
            logger.info(f"[sandbox_flow] Successfully created version bundle snapshot for project {project_id}")
        except Exception as e:
            logger.warning(f"[sandbox_flow] Failed to create version bundle snapshot: {e}")

    finally:
        # ALWAYS release codegen lock here (even if an exception happened)
        try:
            _release_codegen_lock(project_id, session_id=session_id)
        except Exception:
            pass


# ─────────────────────── Edit Design  ────────────────────────────
@app.post("/edit-design")
def edit_design_route(data: CadEditIn, tasks: BackgroundTasks, user=Depends(get_current_user)):
    USER_ID = user["sub"]
    _enforce_ai_quota_or_402(USER_ID)
    session = SESSION_ID()
    current_doc = get_artifact_for_version(data.project_id, "cad_code", data.cad_code_version)
    if not current_doc:
        raise HTTPException(404, "No current CAD code found for this project")
    
    current_code = current_doc["data"]["code"]

    res, usageX = edit_cadquery(current_code, data.user_query)
    new_code = res["code"]
    summary_md = res["summary_md"]

    new_ver = storage.next_version(data.project_id, "cad_code")
    storage.put_artifact(
        data.project_id, USER_ID, session,
        art_type="cad_code", version=new_ver, data={"code": new_code}, parent_id=current_doc.get("id")
    )
    
    # FEATURE TREE SYNC: Update feature tree to reflect CAD code changes
    try:
        sync_success = feature_tree_sync.sync_feature_tree_from_code(
            data.project_id, USER_ID, new_code, new_ver, session
        )
        if sync_success:
            logger.info(f"Feature tree synchronized with CAD code version {new_ver}")
        else:
            logger.warning(f"Feature tree sync failed for project {data.project_id}")
    except Exception as sync_error:
        logger.error(f"Feature tree sync error in edit-design: {sync_error}")
    
    storage.add_chat_message(
        data.project_id, session, USER_ID, "user", data.user_query
    )
    storage.add_chat_message(
        data.project_id, session, USER_ID, "assistant",
        content=summary_md
    )
    export = "stl"
    file_path = None
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            file_path = run_cadquery(new_code)
            last_error = None
            break
        except Exception as e:
            last_error = str(e)
            new_code, usage4 = fix_cadquery(new_code, last_error)
            storage.log_operation(
                    USER_ID, data.project_id, session,
                    op_type="code_fix", agent="o4-mini",
                    tokens_prompt=usage4.prompt_tokens, tokens_comp=usage4.completion_tokens, latency_ms=0,
                )
    if not file_path:
        logger.error("Initial sandbox failed after retries:\n%s", format_exc())
        raise HTTPException(500, f"Initial sandbox failed: {last_error}")
    
    else:
        blob_url, gcs_path = storage.upload_geometry(file_path, data.project_id, new_ver, "stl", ttl_sec=86_400)
        # NEW: log what we uploaded and verify the slot path exists
        try:
            slot_path = storage.geometry_blob_path(data.project_id, new_ver, "stl")
            exists = storage.stl_exists(data.project_id, new_ver)
            logger.info(
                f"[sandbox_flow] STL uploaded: slot_exists={exists} "
                f"slot_path={slot_path} gcs_path={gcs_path}"
            )
        except Exception as ee:
            logger.warning(f"[sandbox_flow] stl_exists check failed: {ee}")
        # record the cad_file artifact
        storage.put_artifact(
            data.project_id, USER_ID, session,
            art_type="cad_file", version=f"{new_ver}", blob_url=blob_url, data={"export": export, "filename": Path(file_path).name, "gcs_path": gcs_path}
        )
    tasks.add_task(_export_step_bg, data.project_id, session, USER_ID, new_code, new_ver, award_on_complete=False)
    return {"new_version": new_ver, "summary_md": summary_md, "code": new_code, "blob_url": blob_url}

# ─────────────────────── Manual sandbox (debug) ─────────────────────
@app.post("/sandbox-run")
def sandbox_run_route(code: str = Body(..., media_type="text/plain")):
    for attempt in range(MAX_RETRIES + 1):
        try:
            stl = run_cadquery(code)
            return {"stl_path": stl, "attempts": attempt}
        except SandboxError as err:
            if attempt == MAX_RETRIES:
                return {"error": str(err), "attempts": attempt}
            code, usage5 = fix_cadquery(code, str(err))

@app.get("/latest-cad")
def latest_cad(
    project_id: str = Query(..., description="Project ID"),
    version: int | None = Query(None, description="CAD viewer slot (design version)"),
    record: Optional[bool] = Query(False, description="If true AND download=true, count as 'exports'"),
    download: Optional[bool] = Query(False, description="Only set true from an explicit Export button"),
    user=Depends(optional_user),
):
    def _sign_from_latest_artifact():
        try:
            arts = storage.list_artifacts(project_id, "cad_file", latest=False) or []
            stls = [a for a in arts if (a.get("data") or {}).get("export") == "stl"]
            if not stls:
                return None, None
            latest_stl = max(stls, key=lambda d: int(d.get("version", 0)))
            data = latest_stl.get("data") or {}
            gcs_path = data.get("gcs_path")
            if not gcs_path:
                return None, None
            v = int(data.get("design_ver") or latest_stl.get("version", 0))
            url = storage.sign_path(gcs_path, ttl_sec=86_400)
            return url, v
        except Exception as e:
            logger.error(f"[latest_cad] artifact fallback failed: {e}")
            return None, None

    def _sign_for_slot(slot: int | None):
        if slot is None:
            return None, None
        v = int(slot)
        if not storage.stl_exists(project_id, v):
            return None, None
        path = storage.geometry_blob_path(project_id, v, "stl")
        url  = storage.sign_path(path, ttl_sec=86_400)
        return url, v

    # 1) Explicit viewer slot requested
    if version is not None:
        url, v = _sign_for_slot(version)
        if not url:
            try:
                meta = C_META.document(project_id).get().to_dict() or {}
                meta_slot = meta.get("cadVersion")
            except Exception:
                meta_slot = None
            url, v = _sign_for_slot(meta_slot)

        if not url:
            try:
                arts = storage.list_artifacts(project_id, "cad_file", latest=False) or []
                stls = [a for a in arts if (a.get("data") or {}).get("export") == "stl"]
                if stls:
                    latest_stl = max(stls, key=lambda d: int(d.get("version", 0)))
                    dv = (latest_stl.get("data") or {}).get("design_ver") or int(latest_stl.get("version", 0))
                    url, v = _sign_for_slot(dv)
            except Exception:
                pass

        if not url:
            url, v = _sign_from_latest_artifact()

        if not url:
            return {"status": "pending"}

        award = None; snap = None
        if record and download and user is not None:
            _enforce_action_or_402(user["sub"], "export_stl")
            try:
                storage.consume_action(user["sub"], "export_stl")
            except Exception:
                pass
            try:
                award = storage.record_progress(user["sub"], "exports",
                                                unique_key=f"{project_id}:stl:{v}")
                snap  = storage.get_progress_snapshot(user["sub"])
            except Exception:
                pass
        return {"status": "ready", "blob_url": url, "version": int(v),
                "award": award, "progressSnapshot": snap}

    # 2) No version provided → use meta.cadVersion, then fallbacks
    try:
        meta = C_META.document(project_id).get().to_dict() or {}
        cad_slot = meta.get("cadVersion")
    except Exception:
        cad_slot = None

    url, v = _sign_for_slot(cad_slot)
    if not url:
        try:
            arts = storage.list_artifacts(project_id, "cad_file", latest=False) or []
            stls = [a for a in arts if (a.get("data") or {}).get("export") == "stl"]
            if stls:
                latest_stl = max(stls, key=lambda d: int(d.get("version", 0)))
                dv = (latest_stl.get("data") or {}).get("design_ver") or int(latest_stl.get("version", 0))
                url, v = _sign_for_slot(dv)
        except Exception:
            pass
    if not url:
        url, v = _sign_from_latest_artifact()
    if not url:
        return {"status": "pending"}

    award = None; snap = None
    if record and download and user:
        _enforce_action_or_402(user["sub"], "export_stl")
        try:
            storage.consume_action(user["sub"], "export_stl")
        except Exception:
            pass
        try:
            award = storage.record_progress(user["sub"], "exports",
                                            unique_key=f"{project_id}:stl:{v}")
            snap  = storage.get_progress_snapshot(user["sub"])
        except Exception:
            pass
    return {"status": "ready", "blob_url": url, "version": int(v),
            "award": award, "progressSnapshot": snap}



@app.post("/edit-brainstorm")
def brainstorm_edit_route(data: BrainstormEditIn, user=Depends(get_current_user)):
    USER_ID = user["sub"]
    _enforce_ai_quota_or_402(USER_ID)
    session = SESSION_ID()
    doc = get_artifact_for_version(data.project_id, "brainstorm", data.brainstorm_version)
    if not doc:
        raise HTTPException(404, "Brainstorm not found")
    current = doc["data"]

    result, usageB = edit_brainstorm(current, data.user_query)
    ver     = storage.next_version(data.project_id, "brainstorm")
    storage.put_artifact(
        data.project_id, USER_ID, session,
        art_type="brainstorm", version=ver, data=result["brainstorm"], parent_id=doc.get("id")
    )
    storage.add_chat_message(
        data.project_id, session, USER_ID, "assistant", result["summary_md"]
    )
    return {"new_version": ver, "brainstorm": result["brainstorm"], "summary_md": result["summary_md"]}

@app.post("/classify")
def classify_route(data: ClassifierIn, user=Depends(get_current_user)):
    USER_ID = user["sub"]
    _enforce_ai_quota_or_402(USER_ID) 
    session = SESSION_ID()
    raw, usage = classify_intents(data.project_id, data.user_query)
    storage.log_operation(
        USER_ID, data.project_id, session,
        op_type="classification", agent="gpt-4.1-mini",
        tokens_prompt=usage.prompt_tokens, tokens_comp=usage.completion_tokens, latency_ms=0,
    )
    return raw

@app.post("/chat")
async def chat_route(data: ChatIn, tasks: BackgroundTasks, user=Depends(get_current_user)):
    USER_ID = user["sub"]
    _enforce_ai_quota_or_402(USER_ID)
    session = SESSION_ID()

    storage.add_chat_message(
        data.project_id, session, USER_ID,
        role="user", content=data.user_query
    )

    KEEPALIVE = "\u2063"          # zero-width; client will ignore it

    async def gen():
        # Send first byte immediately so proxies don’t time out.
        yield KEEPALIVE

        summaries: list[str] = []
        changed_tags: set[str] = set()
        sandbox_task: asyncio.Task | None = None

        try:
            # 1) classify
            result, usageC = classify_intents(
                data.project_id,
                data.user_query,
                data.cad_code_version,
                data.brainstorm_version,
            )
            intents          = result["intents"]
            bstorm_instruct  = result.get("brainstorm_instructions", "")
            design_instruct  = result.get("design_instructions", "")

            storage.log_operation(
                USER_ID, data.project_id, session,
                op_type="classification", agent="gpt-4.1-mini",
                tokens_prompt=usageC.prompt_tokens, tokens_comp=usageC.completion_tokens, latency_ms=0,
            )

            # 2) apply edits (sync), start STL build immediately (await it before speaking)
            for intent in intents:
                try:
                    if intent == "qa":
                        continue

                    if intent == "brainstorm_edit":
                        _enforce_ai_quota_or_402(USER_ID)
                        doc = get_artifact_for_version(data.project_id, "brainstorm", data.brainstorm_version)
                        if doc:
                            res, usage = edit_brainstorm(doc["data"], data.user_query, bstorm_instruct)
                            new_b_ver = storage.next_version(data.project_id, "brainstorm")
                            storage.put_artifact(
                                data.project_id, USER_ID, session,
                                art_type="brainstorm", version=new_b_ver,
                                data=res["brainstorm"], parent_id=doc.get("id")
                            )
                            # ⬅️ make edits visible immediately
                            try:
                                storage.upsert_project_meta(
                                    project_id=data.project_id,
                                    owner_id=USER_ID,
                                    brainVersion=new_b_ver,
                                )
                            except Exception:
                                pass

                            storage.log_operation(
                                USER_ID, data.project_id, session,
                                op_type="edit_brainstorm", agent="gpt-4.1-mini",
                                tokens_prompt=usage.prompt_tokens, tokens_comp=usage.completion_tokens, latency_ms=0,
                            )
                            summaries.append(res["summary_md"])
                            changed_tags.add("Brainstorm")

                    if intent == "cad_edit":
                        _enforce_ai_quota_or_402(USER_ID)
                        doc = get_artifact_for_version(data.project_id, "cad_code", data.cad_code_version)
                        if doc:
                            edit_result, usage1 = edit_cadquery(doc["data"]["code"], data.user_query, design_instruct)
                            storage.log_operation(
                                USER_ID, data.project_id, session,
                                op_type="edit_code", agent="o4-mini",
                                tokens_prompt=usage1.prompt_tokens, tokens_comp=usage1.completion_tokens, latency_ms=0,
                            )

                            new_code   = edit_result["code"]
                            summary_md = edit_result["summary_md"]
                            new_cad_ver = storage.next_version(data.project_id, "cad_code")
                            storage.put_artifact(
                                data.project_id, USER_ID, session,
                                art_type="cad_code", version=new_cad_ver,
                                data={"code": new_code}, parent_id=doc.get("id")
                            )
                            
                            # FEATURE TREE SYNC: Update feature tree to reflect CAD code changes
                            try:
                                sync_success = feature_tree_sync.sync_feature_tree_from_code(
                                    data.project_id, USER_ID, new_code, new_cad_ver, session
                                )
                                if sync_success:
                                    changed_tags.add("Feature Tree")
                                    logger.info(f"Feature tree synchronized with CAD code version {new_cad_ver}")
                                else:
                                    logger.warning(f"Feature tree sync failed for project {data.project_id}")
                            except Exception as sync_error:
                                logger.error(f"Feature tree sync error: {sync_error}")
                            
                            summaries.append(summary_md)
                            changed_tags.add("Design")

                            # ⬇️ Run STL pipeline NOW in a worker thread and wrap in a Task
                            sandbox_task = asyncio.create_task(asyncio.to_thread(
                                _sandbox_flow,
                                data.project_id,
                                session,
                                USER_ID,
                                new_code,
                                new_cad_ver,
                                "stl",
                                False,  # add_message=False (we'll speak after it finishes)
                            ))

                except Exception as exc:
                    summaries.append(f"⚠ `{intent}` failed: {exc}")

            if changed_tags:
                try:
                    snapshot_bundle(
                        project_id=data.project_id,
                        user_id=USER_ID,
                        session_id=session,
                        changed=sorted(changed_tags),
                        summary="• ".join(summaries),
                    )
                except Exception:
                    pass

            # 3) If we edited CAD, WAIT for STL/upload/meta to finish (keep connection alive)
            if sandbox_task is not None:
                while not sandbox_task.done():
                    yield KEEPALIVE
                    await asyncio.sleep(0.5)
                # propagate any exception
                await sandbox_task

        except Exception as exc_all:
            yield f"\n\n⚠ Error during edits: {exc_all}\n"

        # 4) Only now stream the assistant’s answer (first real text)
        full_msg = ""
        try:
            async for chunk in stream_reply(
                user_query=data.user_query,
                summaries=summaries,
                project_id=data.project_id,
            ):
                full_msg += chunk
                yield chunk
        except Exception as e:
            full_msg += f"\n\n⚠ Error generating response: {str(e)}"
            yield f"\n\n⚠ Error generating response: {str(e)}"
        finally:
            try:
                storage.add_chat_message(
                    data.project_id, session, USER_ID,
                    role="assistant", content=full_msg
                )
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/plain")


@app.get("/versions")
def list_version_bundles(project_id: str):
    docs = storage.list_artifacts(project_id, "version_bundle", latest=False)
    docs.sort(key=lambda d: d.get("version", 0), reverse=True)       # newest first
    return [
        {
            "version":   d["version"],
            "changed":   d["data"].get("changed", []),
            "summary":   d["data"].get("summary", ""),
            "brain_ver": d["data"].get("brainstorm_ver"),
            "cad_code_ver": d["data"].get("cad_code_ver"),
            "cad_file_ver": d["data"].get("cad_file_ver"),
        }
        for d in docs
    ]

# @app.get("/export/brainstorm-pdf")
# def export_brainstorm_pdf(project_id: str, version: int | None = None):
#     import weasyprint
#     # 1) load brainstorm JSON (this uses correct IDs when version is provided)
#     doc = get_artifact_for_version(project_id, "brainstorm", version)
#     if not doc:
#         raise HTTPException(404, "Brainstorm not found")
#     data = doc["data"]

#     # 2) render → HTML → PDF
#     html = TEMPLATE.render(b=data)
#     pdf  = weasyprint.HTML(string=html).write_pdf()

#     # 3) stream back
#     filename = f"{data.get('project_name','brainstorm')}.pdf"
#     return StreamingResponse(BytesIO(pdf),
#         media_type="application/pdf",
#         headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# # Custom route handler for share URLs that need meta tags for social media
# @app.get("/s/{slug}")
# async def handle_share_route(slug: str, request: Request):
#     """
#     Handle share URLs with proper meta tags for social media crawlers.
#     Serves HTML with meta tags for bots, redirects to React app for browsers.
#     """
#     user_agent = request.headers.get("user-agent", "").lower()
    
#     # Check if this is a social media crawler/bot
#     social_bots = [
#         "facebookexternalhit", "twitterbot", "linkedinbot", "slackbot",
#         "whatsapp", "telegrambot", "skypebot", "googlebot", "bingbot",
#         "redditbot", "applebot", "crawler", "spider", "bot"
#     ]
    
#     is_bot = any(bot in user_agent for bot in social_bots)
    
#     if is_bot:
#         # Serve HTML with meta tags for social media crawlers
#         return await share_preview_html(slug, request)
#     else:
#         # For regular browsers, we need to serve your React app
#         # This assumes you have a built React app served statically
        
#         # Option 1: If you're serving React from a separate domain/port in production
#         # Just return a simple redirect
#         return HTMLResponse(content=f"""
#         <!DOCTYPE html>
#         <html>
#         <head>
#             <title>Redirecting to Makistry...</title>
#             <script>window.location.href = '{settings.ui_origin}/s/{slug}';</script>
#         </head>
#         <body>
#             <p><a href="{settings.ui_origin}/s/{slug}">Continue to Makistry</a></p>
#         </body>
#         </html>
#         """)

# @app.get("/s/{slug}")
# async def handle_share_route(slug: str, request: Request):
#     user_agent = request.headers.get("user-agent", "").lower()
#     social_bots = [
#         "facebookexternalhit", "twitterbot", "linkedinbot", "slackbot",
#         "whatsapp", "telegrambot", "skypebot", "googlebot", "bingbot",
#         "redditbot", "applebot", "crawler", "spider", "bot",
#     ]
#     is_bot = any(bot in user_agent for bot in social_bots)
#     if is_bot:
#         return await share_preview_html(slug, request)
#     else:
#         return RedirectResponse(
#             url=f"{settings.ui_origin.rstrip('/')}/s/{slug}",
#             status_code=307
#         )

# @app.get("/share/{slug}")
# async def legacy_share_route(slug: str, request: Request):
#     return await handle_share_route(slug, request)

@app.post("/export-step")
def export_step(data: StepExportIn, tasks: BackgroundTasks, user=Depends(get_current_user)):
    USER_ID = user["sub"]
    session = SESSION_ID()

    try:
        # Check action limits
        _enforce_action_or_402(USER_ID, "export_step")
        try:
            storage.consume_action(USER_ID, "export_step")
        except Exception as e:
            logger.warning(f"Failed to consume export_step action: {e}")

        # Check if STEP already exists for this version
        existing = storage.list_artifacts(data.project_id, art_type="cad_file", latest=False)
        for doc in existing:
            doc_data = doc.get("data") or {}
            if doc_data.get("export") == "step":
                src_ver = int(doc_data.get("source_code_ver", doc.get("version", 0)))
                # Match by source code version if specified, otherwise use latest
                if data.cad_code_version is None or src_ver == int(data.cad_code_version):
                    logger.info(f"STEP already exists for {data.project_id}:{src_ver}")
                    try:
                        award = storage.record_progress(
                            USER_ID, "exports", 
                            unique_key=f"{data.project_id}:step:{src_ver}"
                        )
                        snap = storage.get_progress_snapshot(USER_ID)
                    except Exception:
                        award = None
                        snap = None

                    return {
                        "blob_url": doc["blobUrl"],
                        "version": doc["version"],
                        "award": award,
                        "progressSnapshot": snap,
                    }

        # Find the CAD code to export
        if data.cad_code_version:
            art_id = artifact_id("cad_code", data.cad_code_version, data.project_id)
            doc = storage.get_artifact(data.project_id, art_id)
        else:
            doc = latest_artifact(data.project_id, "cad_code")
            
        if not doc:
            logger.error(f"No CAD code found for project {data.project_id}")
            return JSONResponse({"error": "CAD code not found for STEP export"}, status_code=404)

        cad_code = doc["data"]["code"]
        code_ver = int(doc["version"])

        # Try to acquire lock to prevent duplicate exports
        acquired, lock_info = _acquire_step_lock(data.project_id, code_ver)
        if not acquired:
            logger.info(f"STEP export already in progress for {data.project_id}:{code_ver}")
            return JSONResponse({"pending": True}, status_code=202)

        # Start background export
        logger.info(f"Starting background STEP export for {data.project_id}:{code_ver}")
        tasks.add_task(
            _export_step_bg, 
            data.project_id, session, USER_ID, cad_code, code_ver,
            award_on_complete=True
        )
        
        return JSONResponse({"pending": True}, status_code=202)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"STEP export endpoint failed: {e}")
        logger.error(f"Full traceback: {format_exc()}")
        raise HTTPException(500, f"STEP export failed: {str(e)}")

@app.get("/step-url")
def step_url(project_id: str, cad_code_version: int | None = None):
    """Check if STEP file is ready and return download URL"""
    try:
        existing = storage.list_artifacts(project_id, "cad_file", latest=False) or []
        
        for doc in existing:
            doc_data = doc.get("data") or {}
            if doc_data.get("export") == "step":
                src_ver = int(doc_data.get("source_code_ver", doc.get("version", 0)))
                
                # If version specified, check if it matches
                if cad_code_version is not None and src_ver != int(cad_code_version):
                    continue
                    
                logger.info(f"Found STEP file for {project_id}:{src_ver}")
                return {
                    "status": "ready", 
                    "blob_url": doc["blobUrl"], 
                    "version": doc["version"]
                }
                
        logger.info(f"No STEP file found for {project_id}:{cad_code_version}")
        return {"status": "pending"}
        
    except Exception as e:
        logger.error(f"Error checking STEP status: {e}")
        return {"status": "pending"}

@app.get("/api/step-url")
def _api_step_url(project_id: str, cad_code_version: int | None = None):
    return step_url(project_id, cad_code_version)


# --- /api aliases so Hosting rewrite always reaches these routes ---
@app.post("/api/brainstorm")
def _api_brainstorm(data: BrainstormIn, user=Depends(get_current_user)):
    return brainstorm_route(data, user)

@app.post("/api/generate-design")
def _api_generate_design(data: DesignIn, tasks: BackgroundTasks, user=Depends(get_current_user)):
    return generate_design_route(data, tasks, user)

@app.post("/api/edit-design")
def _api_edit_design(data: CadEditIn, tasks: BackgroundTasks, user=Depends(get_current_user)):
    return edit_design_route(data, tasks, user)

@app.get("/api/latest-brainstorm")
def _api_latest_brainstorm(project_id: str = Query(...), version: int | None = Query(None)):
    return latest_brainstorm(project_id, version)

@app.get("/api/latest-cad")
def _api_latest_cad(
    project_id: str = Query(...),
    version: int | None = Query(None),
    record: Optional[bool] = Query(False),
    user=Depends(optional_user),
):
    return latest_cad(project_id=project_id, version=version, record=record, download=False, user=user)

@app.get("/api/versions")
def _api_versions(project_id: str = Query(...)):
    return list_version_bundles(project_id)

@app.post("/api/sandbox-run")
def _api_sandbox_run(code: str = Body(..., media_type="text/plain")):
    return sandbox_run_route(code)

@app.post("/api/export-step")
def _api_export_step(data: StepExportIn, tasks: BackgroundTasks, user=Depends(get_current_user)):
    return export_step(data, tasks, user)

@app.post("/api/edit-brainstorm")
def _api_edit_brainstorm(data: BrainstormEditIn, user=Depends(get_current_user)):
    return brainstorm_edit_route(data, user)

@app.post("/api/classify")
def _api_classify(data: ClassifierIn, user=Depends(get_current_user)):
    return classify_route(data, user)

@app.post("/api/chat")
async def _api_chat(data: ChatIn, tasks: BackgroundTasks, user=Depends(get_current_user)):
    return await chat_route(data, tasks, user)

# --- Brainstorm → PDF (pure-Python) ------------------------------------------
def _brainstorm_to_pdf_bytes(data: dict) -> bytes:
    """Generate PDF from brainstorm data matching the actual JSON structure"""
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    elems = []

    def add_header(txt):
        """Add a section header"""
        elems.append(Spacer(1, 0.2 * inch))
        elems.append(Paragraph(txt, styles["Heading2"]))

    def add_paragraph(txt):
        """Add a paragraph of text"""
        if txt and txt.strip():
            elems.append(Paragraph(txt.strip(), styles["BodyText"]))

    def add_bullet_list(title, items):
        """Add a bulleted list section"""
        if not items:
            return
        add_header(title)
        flow = []
        for item in items:
            if isinstance(item, dict):
                # Handle dict items by joining key-value pairs
                text = ", ".join(f"{k}: {v}" for k, v in item.items())
                flow.append(ListItem(Paragraph(text, styles["BodyText"]), leftIndent=12))
            else:
                # Handle string items
                flow.append(ListItem(Paragraph(str(item), styles["BodyText"]), leftIndent=12))
        elems.append(ListFlowable(flow, bulletType="bullet"))

    # Title and one-liner
    title = data.get("project_name") or "Brainstorm"
    elems.append(Paragraph(title, styles["Title"]))
    elems.append(Spacer(1, 0.15 * inch))

    # One-liner (if present)
    one_liner = data.get("design_one_liner")
    if one_liner:
        elems.append(Paragraph(f"<b>One-liner:</b> {one_liner}", styles["BodyText"]))
        elems.append(Spacer(1, 0.1 * inch))

    # Add all the sections that match your brainstorm structure
    sections = [
        ("key_features", "Key Features"),
        ("key_functionalities", "Key Functionalities"), 
        ("design_components", "Design Components"),
        ("optimal_geometry", "Geometry"),
        ("design_objectives", "Design Objectives"),
        ("design_requirements", "Design Requirements"),
        ("technical_specifications", "Technical Specifications"),
        ("materials", "Materials"),
        ("manufacturing_considerations", "Manufacturing Considerations"),
        ("constraints", "Constraints"),
        ("assumptions", "Assumptions"),
        ("risks_and_challenges", "Risks and Challenges"),
        ("testing_validation", "Testing and Validation"),
        ("implementation_plan", "Implementation Plan"),
        ("success_criteria", "Success Criteria"),
        ("notes", "Additional Notes"),
    ]

    for field_name, display_title in sections:
        field_value = data.get(field_name)
        
        if isinstance(field_value, (list, tuple)) and field_value:
            add_bullet_list(display_title, field_value)
        elif isinstance(field_value, str) and field_value.strip():
            add_header(display_title)
            add_paragraph(field_value.strip())
        elif isinstance(field_value, dict) and field_value:
            # Handle dict fields by converting to key: value format
            add_header(display_title)
            for key, value in field_value.items():
                if value:
                    elems.append(Paragraph(f"<b>{key}:</b> {value}", styles["BodyText"]))

    # Footer
    elems.append(Spacer(1, 0.5 * inch))
    elems.append(Paragraph("Generated by <b>Makistry</b>", styles["BodyText"]))

    doc.build(elems)
    return buf.getvalue()

@app.get("/export/brainstorm-pdf")
def export_brainstorm_pdf(project_id: str, version: int | None = None):
    doc = get_artifact_for_version(project_id, "brainstorm", version)
    if not doc:
        raise HTTPException(404, "Brainstorm not found")
    data = doc["data"]
    pdf = _brainstorm_to_pdf_bytes(data)
    fname = f"{(data.get('project_name') or 'brainstorm').replace(' ', '_')}.pdf"
    return StreamingResponse(BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})

# /api alias so the Hosting rewrite still reaches it
@app.get("/api/export/brainstorm-pdf")
def _api_export_brainstorm_pdf(project_id: str, version: int | None = None):
    return export_brainstorm_pdf(project_id, version)


def _acquire_step_lock(project_id: str, code_ver: int, ttl_s: int = 600):
    """Acquire a lock for STEP export to prevent duplicates"""
    doc = C_META.document(project_id)
    tx = firestore.Client().transaction()
    
    @firestore.transactional
    def _do(t):
        try:
            snap = doc.get(transaction=t)
            data = snap.to_dict() or {}
            locks = data.get("locks") or {}
            key = f"step_export_{int(code_ver)}"  # More specific key
            lock = locks.get(key)
            now = _now_ms()
            
            # Check if lock exists and hasn't expired
            if lock and int(lock.get("expiresAt", 0)) > now:
                logger.info(f"STEP lock already held for {project_id}:{code_ver}")
                return False, lock
                
            # Acquire new lock
            new_lock = {
                "owner": "step_export", 
                "session": f"step_{code_ver}_{uuid.uuid4().hex[:8]}", 
                "startedAt": now, 
                "expiresAt": now + ttl_s * 1000
            }
            locks[key] = new_lock
            t.set(doc, {"locks": locks}, merge=True)
            logger.info(f"Acquired STEP lock for {project_id}:{code_ver}")
            return True, new_lock
            
        except Exception as e:
            logger.error(f"Error acquiring STEP lock: {e}")
            return False, None
            
    return _do(tx)


def _release_step_lock(project_id: str, code_ver: int):
    """Release the STEP export lock"""
    doc = C_META.document(project_id)
    tx = firestore.Client().transaction()
    
    @firestore.transactional
    def _do(t):
        try:
            snap = doc.get(transaction=t)
            data = snap.to_dict() or {}
            locks = data.get("locks") or {}
            key = f"step_export_{int(code_ver)}"
            
            if key in locks:
                locks.pop(key, None)
                t.set(doc, {"locks": locks}, merge=True)
                logger.info(f"Released STEP lock for {project_id}:{code_ver}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error releasing STEP lock: {e}")
            return False
            
    return _do(tx)
