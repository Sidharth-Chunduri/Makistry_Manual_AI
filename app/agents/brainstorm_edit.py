"""
Brainstorm-edit agent — uses gpt-4.1-mini
Takes current brainstorm JSON + user instruction → edited brainstorm JSON + summary_md.
"""
from typing import Dict, Optional
from app.agents._utils import openai_client, _strip_fence, _json_or_raise
import json
from app.core.config import settings

_client = openai_client()
MODEL   = settings.bstorm_edit_model      # point to 4.1-mini deployment

_SCHEMA = """Return ONLY valid JSON:
{
  "brainstorm": { ...full updated brainstorm JSON... },
  "summary_md": "• bullet list of changes"
}"""

_SYSTEM = (
    "You are a brainstorming *editor*. Given the *current* brainstorm JSON, a change request query, and a specific instruction, update ALL necessary fields, propagate changes to other fields only if neccesary for correctness and completeness.\n"
    "Then, list the edits you made succinctly.\n"
    "Ensure all responses are succinct, relevant, practically feasible, technically sound, creative, and clear using a formal yet approachable tone with non-technical language.\n"
    "Consider the design intent, use cases, and existing designs to generate innovative design information.\n"
    "Ensure all values are concrete, not ranges, and have appropriate units.\n" 
    "If values are provided, use those, otherwise use your best judgement.\n" 
    "Always double-check and update geometric information for all appropriate components to ensure it is always accurate and aligned with changes.\n"
    "ALWAYS return the *full* updated Brainstorm JSON.\n"
    "Remove underscores in the JSON key names in the edit summary.\n"
    + _SCHEMA
)

def edit_brainstorm(current: Dict, user_query: str, instruction: Optional[str]) -> Dict:
    user_block = (
        "CURRENT_BRAINSTORM_JSON:\n```json\n"
        + json.dumps(current, indent=2)
        + "\n```\n\nUSER_REQUEST:\n"
        + user_query
    )
    if instruction and instruction.strip():
        user_block += "\n\nSPECIFIC_INSTRUCTIONS:\n" + instruction.strip()
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": user_block}
    ]
    resp = _client.chat.completions.create(
        model = MODEL,
        messages = messages,
        max_completion_tokens = 1500,
        temperature = 0.4,
        # response_format={"type":"json_object"}   # enable when your deployment is on 2025-05-15+ API
    )
    content = resp.choices[0].message.content or ""
    if not content.startswith("{"):
        content = _strip_fence(content)

    result = _json_or_raise(content, "brainstorm-edit")
    if "brainstorm" not in result or "summary_md" not in result:
        raise RuntimeError("brainstorm-edit missing keys")
    return result, resp.usage