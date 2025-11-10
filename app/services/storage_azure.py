"""
app/services/storage.py
───────────────────────
Centralised helpers for

• Azure Cosmos DB (NoSQL / Core SQL API)
  - identity, operations, artifacts, chat_history containers
• Azure Blob Storage  (large CAD / mesh / FEA files)
• Minimal password hashing + JWT (can be swapped for AD B2C later)

All env-vars are loaded from app.core.config.settings
"""

from __future__ import annotations

import datetime as _dt
import json, uuid, secrets, bcrypt
from pathlib import Path
from typing import Any, Dict, Optional
import tempfile
from uuid import uuid4
import jwt                              # PyJWT
from azure.cosmos import CosmosClient, PartitionKey
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
    BlobClient,
)

from app.core.config import settings    # <- your .env loader

# ───────────────────────── Cosmos initialisation ──────────────────────────
_cosmos = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)  # type: ignore
_db = _cosmos.create_database_if_not_exists(settings.cosmos_db)

def _container(name: str, pk: str):
    return _db.create_container_if_not_exists(name, PartitionKey(pk))

c_identity   = _container("identity",   "/userID")
c_operations = _container("operations", "/projectID")
c_artifacts  = _container("artifacts",  "/projectID")
c_chat       = _container("chat_history", "/sessionID")

# ───────────────────────── Blob initialisation ────────────────────────────
_blob = BlobServiceClient(
    f"https://{settings.blob_account}.blob.core.windows.net",
    credential=settings.blob_key,
)

blob_container = _blob.get_container_client(settings.blob_container)
try:
    blob_container.create_container()           # first-time create
except ResourceExistsError:
    pass                                        # it already exists – OK


# ======================================================================
#  Identity helpers
# ======================================================================
def _hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def _verify_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def signup(email: str, password: str) -> str:
    email = email.lower()
    user_id = f"user_{uuid.uuid4().hex[:8]}"
    c_identity.create_item({
        "id": email,               # doc id
        "userID": user_id,
        "email": email,
        "password": _hash_pw(password),
        "createdAt": _dt.datetime.utcnow().isoformat(),
        "projects": [],            # will store projectIds
        "tokenUsage": {},          # per-agent totals
    })
    return user_id

def login(email: str, password: str) -> str | None:
    email = email.lower()
    try:
        doc = c_identity.read_item(email, partition_key=email)
    except Exception:
        return None
    if not _verify_pw(password, doc["password"]):
        return None

    # update lastLogin
    doc["lastLogin"] = _dt.datetime.utcnow().isoformat()
    c_identity.upsert_item(doc)

    payload = {
        "sub": doc["userID"],
        "email": email,
        "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=24),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

# ======================================================================
#  Project & artifact helpers
# ======================================================================
def _now_iso() -> str:
    return _dt.datetime.utcnow().isoformat()

def create_project(user_id: str) -> str:
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    # add to user's project list (best-effort)
    try:
        query = "SELECT * FROM c WHERE c.userID=@u"
        user_doc = list(c_identity.query_items(
            query,
            parameters=[{"name":"@u","value":user_id}],
            enable_cross_partition_query=True
        ))[0]
        user_doc.setdefault("projects", []).append(project_id)
        c_identity.upsert_item(user_doc)
    except Exception:
        pass
    # no separate project container needed; first artifact will create a partition
    return project_id

# ---------- artifacts --------------------------------------------------
def put_artifact(
    project_id: str,
    user_id: str,
    session_id: str,
    art_type: str,
    data: Dict[str, Any],
    version: int | None = None,
    parent_id: str | None = None,
    blob_url: str | None = None,
    tags: Optional[list[str]] = None,
):
    if version is None:
        version = next_version(project_id, art_type)

    art_id = f"{art_type}_{version}"
    
    art_id = f"{art_type}_{version or uuid.uuid4().hex[:6]}"
    c_artifacts.upsert_item({
        "id": art_id,
        "projectID": project_id,
        "userID": user_id,
        "sessionID": session_id,
        "type": art_type,
        "version": version,
        "parentID": parent_id,
        "createdAt": _now_iso(),
        "blobUrl": blob_url,
        "tags": tags or [],
        "data": data,
    })
    return art_id

def get_artifact(project_id: str, art_id: str) -> Optional[Dict[str, Any]]:
    try:
        return c_artifacts.read_item(art_id, partition_key=project_id)
    except Exception:
        return None
def _version_to_int(v):
    """
    Return an int for sorting:
      • int   → as-is
      • str   → numeric prefix before non-digits, else 0
      • None  → 0
    """
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        num = ""
        for ch in v:
            if ch.isdigit():
                num += ch
            else:
                break
        return int(num) if num else 0
    return 0

def list_artifacts(project_id: str,
                   art_type: str | None = None,
                   latest: bool = False):
    """
    Return all artefacts for a project, optionally filtered by type.
    If *latest* is True, return only the newest version.
    """
    query = "SELECT * FROM c WHERE c.projectID = @pid"
    params = [{"name": "@pid", "value": project_id}]
    if art_type:
        query += " AND c.type = @type"
        params.append({"name": "@type", "value": art_type})

    items = list(c_artifacts.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=True,
    ))

    if latest and items:
        items.sort(key=lambda d: _version_to_int(d.get("version", 0)))
        return items[-1]
    return items

def last_chat_messages(project_id: str, limit: int = 20):
    """
    Return the latest *limit* chat messages for a project,
    ordered oldest→newest.   You can extend to filter by sessionID if needed.
    """
    query = (
        "SELECT TOP @n * FROM c "
        "WHERE c.projectID = @pid "
        "ORDER BY c._ts DESC"
    )
    params = [{"name": "@n", "value": limit},
              {"name": "@pid", "value": project_id}]
    docs = list(c_chat.query_items(query, parameters=params,
                                   enable_cross_partition_query=True))
    return list(reversed(docs))   # oldest first


# ---------- operations -------------------------------------------------
def log_operation(
    user_id: str,
    project_id: str,
    session_id: str,
    op_type: str,
    agent: str,
    tokens_prompt: int = 0,
    tokens_comp: int = 0,
    latency_ms: int = 0,
    status: str = "success",
    error: Optional[str] = None,
    design_stage: Optional[str] = None,
    retry: int = 0,
):
    c_operations.create_item({
        "id": f"{op_type}:{project_id}:{uuid4().hex[:8]}",
        "userID": user_id,
        "projectID": project_id,
        "sessionID": session_id,
        "ts": _now_iso(),
        "operationType": op_type,
        "agent": agent,
        "tokens": {
            "prompt": tokens_prompt,
            "completion": tokens_comp,
            "total": tokens_prompt + tokens_comp,
        },
        "latency": latency_ms,
        "status": status,
        "error": error,
        "retryAttempts": retry,
        "designStage": design_stage,
    })

# ---------- chat -------------------------------------------------------
def add_chat_message(
    project_id: str,
    session_id: str,
    user_id: str,
    role: str,                      # "user" or "assistant"
    content: str,
    agent: Optional[str] = None,
    op_id: Optional[str] = None,
    tokens_prompt: int = 0,
    tokens_comp: int = 0,
    design_stage: Optional[str] = None,
):
    c_chat.create_item({
        "id": str(uuid.uuid4()),
        "projectID": project_id,
        "sessionID": session_id,
        "userId": user_id,
        "role": role,
        "agent": agent,
        "content": content,
        "tokens": {
            "prompt": tokens_prompt,
            "completion": tokens_comp,
            "total": tokens_prompt + tokens_comp,
        },
        "designStage": design_stage,
        "relatedOp": op_id,
        "ts": _now_iso(),
    })

# ------------------------------------------------------------------
#  Blob helpers
# ------------------------------------------------------------------
def upload_blob(local_path: str, project_id: str, subdir: str,
                ttl_sec: int = 3600) -> str:
    """
    • Upload *local_path* to `project_id/subdir/filename`
    • Return a time-limited HTTPS URL you can hand to the front-end.
    """
    file_name  = Path(local_path).name
    blob_path  = f"{project_id}/{subdir}/{file_name}"

    # Pick content-type
    ctype = "application/octet-stream"
    if file_name.endswith(".stl"):
        ctype = "model/stl"
    elif file_name.endswith(".obj"):
        ctype = "text/plain"

    with open(local_path, "rb") as fh:
        blob_container.upload_blob(
            blob_path, fh, overwrite=True,
            content_settings=ContentSettings(content_type=ctype),
        )

    sas = generate_blob_sas(
        account_name=settings.blob_account,
        account_key=settings.blob_key,
        container_name=settings.blob_container,
        blob_name=blob_path,
        permission=BlobSasPermissions(read=True),
        expiry=_dt.datetime.utcnow() + _dt.timedelta(seconds=ttl_sec),
    )
    return f"{blob_container.url}/{blob_path}?{sas}"

def next_version(project_id: str, art_type: str) -> int:
    """
    Return 1 + current max version for (project_id, art_type).
    Non-ints treated as 0.
    """
    items = list_artifacts(project_id=project_id, art_type=art_type, latest=False)
    if not items:
        return 1
    max_v = 0
    for it in items:
        v = it.get("version")
        try:
            v = int(v)
        except Exception:
            v = 0
        if v > max_v:
            max_v = v
    return max_v + 1

def download_blob_to_temp(blob_url: str) -> str:
    """
    Download a blob from Azure Storage into a temp file and
    return the local filesystem path.
    """
    # create a client directly from the URL
    from urllib.parse import urlparse

    client = BlobClient.from_blob_url(blob_url)
    stream = client.download_blob().readall()

    parsed = urlparse(blob_url)
    ext = Path(parsed.path).suffix or ""

    # make a temp file (auto‐deleted on reboot)
    fd, path = tempfile.mkstemp(suffix=ext)
    with open(path, "wb") as f:
        f.write(stream)
    return path