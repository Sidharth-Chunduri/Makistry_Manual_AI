# app/agents/planner.py
"""
Planning agent for Makistry.
Translates brainstorm JSON ➜ build-plan JSON for the coding agent.
Uses the o4-mini model deployed on Azure AI Foundry.
"""

from typing import Dict
import json, logging, re
from openai import AzureOpenAI
from app.core.config import settings

_client = AzureOpenAI(
    api_version=settings.plan_api_ver,     # e.g. "2025-06-01-preview"
    azure_endpoint=settings.endpoint,
    api_key=settings.api_key,
)
_JSON_PAT = re.compile(r"\{.*\}", re.S)   # greedy match first {...}

def _safe_to_json(raw: str) -> Dict:
    m = _JSON_PAT.search(raw)
    if not m:
        raise RuntimeError("No JSON object found in model reply")
    return json.loads(m.group(0))

SCHEMA = """
Return ONLY valid JSON with keys exactly as follows:
- units: string 
- global frame: include origin and axes (X=length, Y=width, Z=height/thickness)
- components: list of all parts of the design, for each component:
    - name: string (snake_case, descriptive)
    - method: string (extrude | revolve | loft | sweep | shell | boolean-cut)
    - params: object of all accurate, exact, complete, and necessary parameters (numerical values, like integers or floats, no strings) for the method
    - anchor: (center | bottom_face_center | corner | etc.)
    - steps: ordered list of operations and numerical parameteres to be followed to create the component
- assembly: list of {child, parent, attach:{child_anchor, parent_face (cq selector), offset (after mating), rotate (degree about X,Y,Z)}}
- acceptance_tests: list of simple strings the validator can check
Hard constraints:
- Do NOT use nested arrays. Example: [[x,y]] is forbidden. Use [{x,y}] instead.
- All numeric values must be numbers, not strings, and finite (no NaN/Inf).
- Keep field names EXACT; prefer snake_case for component names.
- No markdown, no comments, no extra keys.
"""

_SYSTEM_MSG = (
    "Role: You are the CadQuery planning agent for Makistry with focus on reliability and precision.\n"
    "Goal: Convert brainstorm JSON (containing components, key features, geometric information, etc.) into a robust, executable, and complete build-plan JSON for CadQuery 2.5.2 coding agent to follow to achieve the design requirements."
    "Critical Rules:\n"
    "1. ALL numerical values must be concrete numerical values only (float/int), with appropriate units for all numbers, never strings\n"
    "2. Provide complete parameter sets - missing parameters cause failures\n"
    "3. Plan for assembly constraints - components must be positioned correctly, add specific anchor points for reliable assembly\n"
    "4. Ensure the build-plan covers all the requirements outlined in the brainstorm JSON, however, include reasonable values when brainstorm lacks specifics\n"
    "5. Think step-by-step thoroughly and internally, focus on design modularity and maintaining sufficient detail, nuances, complexity, and intricacies in the CAD model.\n"
    "Validation:\n"
    "- Each component must be manufacturable as a single, closed, watertight solid\n"
    "- Assembly order must respect dependencies\n"
    "- All dimensions must be positive and reasonable\n"
    "- Method parameters must match CadQuery 2.5.2 API exactly\n"
    + SCHEMA
)

def make_plan(brainstorm: Dict) -> Dict:
    resp = _client.chat.completions.create(
        model=settings.plan_model,          # e.g. "o4-mini"
        messages=[
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user",
             "content": "Brainstorm JSON:\n```json\n"
                        + json.dumps(brainstorm, indent=2)
                        + "\n```\nReturn the build-plan JSON."},
        ],
        max_completion_tokens=20000,
        #temperature=0.35,
    )
    content = resp.choices[0].message.content.strip()
    print("Here is what it said: " + content)
    if content.startswith("```"):
        content = content.split("```", 2)[1]
    try:
        return _safe_to_json(content), resp.usage
    except Exception as exc:
        logging.exception("Planner returned invalid JSON")
        raise RuntimeError(f"Planner JSON error:\n{content}") from exc
