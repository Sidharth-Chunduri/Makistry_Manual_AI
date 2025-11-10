"""
Code-editing agent for Makistry (GPT-4.1-mini on Azure).

Two entry points:
  • fix_cadquery_error(code, error)  – sandbox ➜ agent ➜ fixed code
  • edit_cadquery_query(code, user_instruction) – chat UI ➜ agent ➜ new code
"""

from __future__ import annotations
import logging, textwrap
from openai import AzureOpenAI
from app.core.config import settings
import json, re
from textwrap import dedent
from typing import Optional

_client = AzureOpenAI(
    azure_endpoint=settings.endpoint,
    api_key=settings.api_key,
    api_version=settings.code_edit_api_ver,
)
MODEL = settings.code_edit_model

def _strip_fence(text: str) -> str:
    """
    Remove ``` fences **and** a leading “python” tag line if present,
    returning clean CadQuery code.
    """
    if "```" in text:
        # keep the block that actually contains CadQuery
        blocks = [b for b in text.split("```") if "import cadquery" in b]
        text = blocks[0] if blocks else text.split("```")[1]

    text = text.lstrip()
    if text.lower().startswith("python"):
        text = text.split("\n", 1)[1] if "\n" in text else ""

    return text

# ───────────────────── 1. Sandbox-driven fix ────────────────────────────
_SYSTEM_ERR = (
    "Role: CadQuery debugging expert for Makistry\n"
    "Goal: Fix the provided CADQuery script (version 2.5.2) to elimintate the given an error message, while maintaining functionality, executability, and make sure it produces a single closed, watertight solid.\n"
    "Analysis method:\n"
    "1. Identify the root cause of the error\n"
    "2. Apply targeted fixes\n"
    "3. Ensure the fix doesn not break other parts of the code\n"
    "4. Ensure the code is executable and the design is a single watertight, closed solid\n"
    "Rules:\n"
    "1. Preserve original intent, names, parameters, functionalities, syntax, and structure whenever possible\n"
    "2. Fix ALL occurances of the cause of the error. Propagate changes to other sections of the script as needed\n"
    "3. If a method is invalid, replace it with a working alternative. Use reliable, proven CadQuery patterns, methods, and functions\n"
    "4. Always look to simplify the code and remove unnecessary complexity, whenever possible during editing, while maintaining correctness and functionality\n"
    "5. No comments, docstrings, explanations, or extra text\n"
    "Return ONLY the fully corrected CadQuery script that runs without errors.\n"
)

def fix_cadquery (code: str, error: str, system_prompt: str | None = None) -> str:
    prompt = textwrap.dedent(f"""
        <SCRIPT>
        ```python
        {code}
        ```
        </SCRIPT>

        <ERROR>
        ```
        {error}
        ```
        </ERROR>

        Return the corrected script inside a single ```python block
    """)
    resp = _client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system_prompt or _SYSTEM_ERR},
                  {"role": "user", "content": prompt}],
        max_completion_tokens=16000,
        #temperature=0.2,
    )
    content = resp.choices[0].message.content or ""
    return _strip_fence(content), resp.usage  # clean up the code, remove fences and leading “python” tag


# ───────────────────── 2. User-driven design edit ───────────────────────
_SCHEMA = """
Return ONLY valid JSON:
{
  "code": "FULL updated CadQuery script",
  "summary_md": "- concise bullet list of visible design changes (no code-level or comment changes)"
}
"""
_SYSTEM_EDIT = (
    "Role: CadQuery design editing expert for Makistry\n"
    "Goal: Modify CadQuery 2.5.2 code to implement the user's design changes while ensuring the code is executable and produces a single closed, watertight solid.\n"
    "Principles:\n"
    "1. Implement changes precisely and completely as per the user's request and specific instructions; do not add unrelated features\n"
    "2. Preserve original intent, names, parameters, functionalities, modularity, syntax, and structure whenever possible\n"
    "3. Prefer simple, reliable operations, using proven CadQuery patterns whenever possible\n"
    "4. Consider about how the design code edits affect other sections of the code and propagate changes as needed\n"
    "5. Do not add comments, docstrings, or extraneous text to the code\n"
    "6. Ensure final result remains exportable and does not break existing geometry\n"
    "7. If the user's request in already a part of the code, check if it is implemented correctly and if there is an assembly, positioning, orientation, or alignment issue and fix it."
    "Rules:\n"
    "- Test and validate intermediate results during modifications\n"
    "- Prefer incremental changes over complete rewrites\n"
    "- Output should be strict JSON (no trailing commas or comments)\n"
    "- Escape backslashes as \\\\ and newlines as \\n inside the JSON string.\n"
    "- Do not start lines with a stray backslash (e.g., \\outer is invalid JSON).\n"
    "Return ONLY the fully updated CadQuery script that runs without errors and a summary of changes.\n" + _SCHEMA
)

def edit_cadquery(code: str, user_query: str, instruction: Optional[str]) -> str:
    prompt = textwrap.dedent(f"""
        USER REQUEST:
        \"\"\"{user_query}\"\"\"

        CURRENT SCRIPT:
        ```python
        {code}
        ```
        --- end of script ---

        Update the script to satisfy the user's request and return ONLY JSON exactly as specified.
    """)
    if instruction and instruction.strip():
        prompt += "\n\nSPECIFIC INSTRUCTIONS:\n" + instruction.strip()
    resp = _client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": _SYSTEM_EDIT},
                  {"role": "user", "content": prompt}],
        max_completion_tokens=16000,
        #temperature=0.3,
    )

    content = resp.choices[0].message.content or ""
    # strip ```json fences
    if not content.startswith("{") and "```" in content:
        content = content.split("```", 2)[1].strip()
    # NEW: strip lone language tag
    content = content.lstrip()
    if content.lower().startswith("json"):
        content = content[4:].lstrip()

    def _maybe_strip_md_fence(x: str) -> str:
        if not x.startswith("{") and "```" in x:
            x = x.split("```", 2)[1].strip()
        x = x.lstrip()
        if x.lower().startswith("json"):
            x = x[4:].lstrip()
        return x

    # 1) First parse attempt
    try:
        data = json.loads(content)
    except Exception:
        logging.warning("edit_cadquery: first JSON parse failed, attempting auto-repair")
        # 2) Ask the model to repair into strict JSON (one-shot)
        repair_prompt = dedent(f"""
        You produced invalid JSON. Fix ONLY escaping/formatting so it becomes strict JSON
        with keys "code" and "summary_md". Do not change the semantics.
        Return ONLY strict JSON.
        ----
        {content}
        ----
        """)
        resp2 = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a JSON repair tool. Output strict JSON only."},
                {"role": "user", "content": repair_prompt},
            ],
            max_completion_tokens=4096,
        )
        repaired = resp2.choices[0].message.content or ""
        repaired = _maybe_strip_md_fence(repaired)
        try:
            data = json.loads(repaired)
        except Exception as exc:
            logging.exception("edit_cadquery: JSON repair also failed")
            # Preserve original content in error so callers can try fallbacks
            raise RuntimeError(f"Bad JSON from cad-edit:\n{content}") from exc

    data["code"] = _strip_fence(data["code"])  # clean up the code
    return data, resp.usage