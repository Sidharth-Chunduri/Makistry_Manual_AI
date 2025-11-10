# app/agents/_utils.py
import json, logging, re
from openai import AzureOpenAI
from app.core.config import settings

def _strip_fence(text: str) -> str:
    """Remove ``` fences + optional language tag."""
    if "```" in text:
        # keep the block containing a brace
        text = next((b for b in text.split("```") if "{" in b), text)
    text = text.lstrip()
    return re.sub(r"^(json|python)\s+", "", text, flags=re.I).strip()

def _json_or_raise(raw: str, ctx: str):
    try:
        return json.loads(raw)
    except Exception as exc:
        logging.exception("%s returned invalid JSON", ctx)
        raise RuntimeError(f"{ctx} invalid JSON:\n{raw}") from exc

def openai_client():
    return AzureOpenAI(
        azure_endpoint=settings.endpoint,
        api_key=settings.api_key,
        api_version=settings.bstorm_api_ver,   # all 4.1-mini deployments share version
    )
