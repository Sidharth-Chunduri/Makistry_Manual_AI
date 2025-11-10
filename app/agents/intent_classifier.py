"""
Intent-classifier for Makistry.
✓ Returns {"intents":[…], "rationale":[…], "confidence":float}
✓ Uses gpt-4.1-mini
"""

from typing import Dict, List
import json, logging, html

from openai import AzureOpenAI
from app.core.config import settings
from app.services import storage            # ← now uses list_artifacts()
from app.services.storage import last_chat_messages
from app.routes.helpers import artifact_id

# ───────────────────────── OpenAI client ──────────────────────────
_client = AzureOpenAI(
    azure_endpoint=settings.endpoint,
    api_key=settings.api_key,
    api_version=settings.intent_api_ver,
)
MODEL = settings.intent_model               # 4.1-mini deployment

# ───────────────────────── Helpers ────────────────────────────────
def _has_artifact(project_id: str, art_type: str) -> bool:
    """True if ≥1 artefact of *art_type* exists for *project_id*."""
    try:
        return bool(storage.list_artifacts(project_id, art_type))
    except Exception as exc:
        logging.exception("_has_artifact failed")
        return False

def _artefact_flags(project_id: str) -> str:
    """
    Return flag string e.g. '110'  (brainstorm, cad, sim)
    1 = present, 0 = absent
    """
    bs  = _has_artifact(project_id, "brainstorm")
    cad = _has_artifact(project_id, "cad_code")
    return f"{int(bs)}{int(cad)}"

def _brainstorm_slice(project_id: str, version: int | None) -> dict | None:
    if version is not None:
        aid = artifact_id("brainstorm", version, project_id)
        doc = storage.get_artifact(project_id, aid)
    else:
        doc = storage.list_artifacts(project_id, "brainstorm", latest=True)
    if not doc:
        return None
    data = doc["data"] or {}
    return {k: data.get(k) for k in _BRAINSTORM_KEYS if k in data}

def _cad_code_snippet(project_id: str, version: int | None) -> tuple[int | None, str | None]:
    if version is not None:
        aid = artifact_id("cad_code", version, project_id)
        doc = storage.get_artifact(project_id, aid)
    else:
        doc = storage.list_artifacts(project_id, "cad_code", latest=True)
    if not doc:
        return None, None
    code = doc["data"].get("code", "")
    return doc.get("version"), code

def _chat_tail(project_id: str, limit: int = 12) -> list[dict]:
    try:
        msgs = last_chat_messages(project_id, limit=limit) or []
    except Exception:
        logging.exception("last_chat_messages failed")
        return []
    return msgs

def _pack_context(project_id: str, cad_code_version: int | None = None, brainstorm_version: int | None = None,) -> str:
    bs = _brainstorm_slice(project_id, brainstorm_version)
    cad_ver, code = _cad_code_snippet(project_id, cad_code_version)
    chat = _chat_tail(project_id)

    parts = []
    if bs:
        parts.append("<brainstorm>\n" + json.dumps(bs, ensure_ascii=False) + "\n</brainstorm>")
    if code:
        # escape to avoid accidental tag breaks
        parts.append(f"<cad_code version='{cad_ver}'>\n" + html.escape(code) + "\n</cad_code>")
    if chat:
        chat_lines = "\n".join(f"{m['role']}: {m['content']}" for m in chat)
        parts.append(f"<chat k='{len(chat)}'>\n{chat_lines}\n</chat>")
    return "<context>\n" + ("\n".join(parts) if parts else "") + "\n</context>"

# ───────────────────────── Constants ──────────────────────────────
_INTENT_LIST = [
    "qa",
    "brainstorm_edit",
    "cad_edit",
]

# Canonical field names (keep ≤ 15 keys each to stay tiny)
_BRAINSTORM_KEYS = [
    "project_name", "key_features", "design_components",
    "optimal_geometry",
]

_SCHEMA = """
Return ONLY valid JSON:
{
  "intents": [ ...subset of ["qa","brainstorm_edit","cad_edit"]... ],
  "brainstorm_instructions": [specific instructions for brainstorm_edit]
  "design_instructions": [specific instructions for design_edit]
}
"""

_SYSTEM = (
    "You are an intent-classifier for an AI product-design assistant.\n"
    "Decide which actions the system should take **given the current artifact state**, common field names, "
    "and the user's query. Multiple intents are allowed; chose the most appropriate ones only. Having the common field in the query does not necessary mean it needs to be edited, consider directness in edit requests.\n\n"
    "Here are some guidelines:\n State flags (bs, cad) (1-present, 0-missing) → allowed intents:"
    "10 : ['qa', 'brainstorm_edit']\n"
    "11 : ['qa', 'brainstorm_edit', 'cad_edit']\n"
    "If 11 and the query is about the design, then include 'cad_edit' and 'brainstorm_edit'."
    "If intent is qa, don't include instructions.\n"
    "For the instructions, reference the code and brainstorm for context and values and propose changes to minimal fields based on user's query. If the user has given exact values, used them, if not, ensure the edits are ALWAYS consistent for all intents and give exact numerical values for all edits.\n"
    "Here are the common field names for brainstorm to help with classification:\n"
    "Brainstorm keys: " + ", ".join(_BRAINSTORM_KEYS) + "\n\n" + _SCHEMA
)

# ───────────────────────── Main function ──────────────────────────
def classify_intents(project_id: str, user_query: str, cad_code_version: int | None = None, brainstorm_version: int | None = None,) -> Dict:
    flags = _artefact_flags(project_id)
    ctx   = _pack_context(project_id, cad_code_version, brainstorm_version)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": (
             f"<state flags='{flags}'/>\n" +
             ctx +
             "\n<query>\n" + user_query + "\n</query>"
         )},
    ]

    resp = _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_completion_tokens=300,
        temperature=0.1,
        # response_format={"type":"json_object"}  # enable when deployment supports it
    )
    content = resp.choices[0].message.content.strip()

    # strip fences if present
    if not content.startswith("{") and "```" in content:
        content = content.split("```", 2)[1].strip()

    try:
        data = json.loads(content)
    except Exception as exc:
        raise RuntimeError(f"intent-classifier bad JSON:\n{content}") from exc
    
    def _to_str(x):
        if x is None: 
            return ""
        if isinstance(x, list):
            return "\n".join(str(i) for i in x)
        return str(x)
    
    data.setdefault("brainstorm_instructions", "")
    data.setdefault("design_instructions", "")
    data["brainstorm_instructions"] = _to_str(data.get("brainstorm_instructions"))
    data["design_instructions"]     = _to_str(data.get("design_instructions"))

    missing = {"intents"} - data.keys()
    if missing:
        raise RuntimeError(f"intent-classifier missing keys: {missing}")

    return data, resp.usage