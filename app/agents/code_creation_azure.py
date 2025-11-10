"""
Generate CADQuery code from brainstorm JSON using Azure OpenAI (GPT-4o / GPT-4o-mini).
"""

from __future__ import annotations

import json, logging
from typing import Dict

from openai import AzureOpenAI
from app.core.config import settings          # loads endpoint / key / model ids

# ── warm global client ---------------------------------------------------------
_client = AzureOpenAI(
    api_version=settings.code_api_ver,        # e.g. 2024-02-15-preview
    azure_endpoint=settings.endpoint,         # AZURE_OAI_ENDPOINT
    api_key=settings.api_key,                 # AZURE_OAI_KEY
)

MODEL = settings.code_model

# _SYSTEM_MSG = (
#     "Role: Export CadQuery code generator for Makistry, focused on reliability and correctness\n"
#     "Goal: Generate robust, executable CadQuery 2.5.2 code that produces a single closed, watertight solid, given a build-plan JSON.\n\n"
#     "Rules:\n"
#     "1. Build the solid incrementally while ensuring high quality, functionality, and sufficient nuances, intricacies, and complexity in the final design\n"
#     "2. Return a single, complete, watertight, closed 'result' solid: asm.toCompound(), combine(), or other appropriate methods.\n"
#     "3. Follow the build-plan thoroughly and exactly, including units, steps, dimensions, etc. Honor each component's anchor and every assembly attach rule (use 'cq.Assembly()'; do not discard transforms via direct union) to assemble all components with correct mates.\n"
#     "4. Follow axis conventions: X=length, Y=width, Z=height/thickness."
#     "5. Ensure the code is modular, complete, working, and correct in syntax and functionality. Make sure all the names are defined.\n"
#     "6. DO NOT include comments, explanations, docstrings, or extraneous text in the code.\n"
#     "7. Export the final object as a STL file.\n"
#     "Post-conditions:\n"
#     "Code must run under Python 3.10 + CadQuery 2.5.2 without errors.\n"
#     "Produces a closed, watertight solid suitable for STL export.\n"
# )

# _SYSTEM_MSG = (
#     "Given a detailed build plan, return ONLY accurate, comprehensive, and working CADQuery-Python code (version 2.5.2) that builds one geometrically valid, watertight, closed, solid body representing the described design.\n\n"
#     "The final object must be a single watertight solid: fuse all sub-parts (use combine(), .union(), or other appropraite methods as needed).\n\n"
#     "Prioritize modularity, simplicity, correctness, and completeness in syntax and functionality, ensuring the code executes without errors. Ensure correct indentation and no missing parentheses. Always define either 'build()' or 'result = Workplane(...)'.\n\n"
#     "Ensure all names are defined and used correctly, and that the code is free of syntax errors.\n\n"
#     "Avoid chamfering and filleting whenever possible, and if it is necessary, double-check the syntax and parameters.\n\n"
#     "Export the final object as a STL file named 'model.stl'."
# )

_SYSTEM_MSG = (
    "Given detailed design information, return ONLY accurate, comprehensive, and working CADQuery-Python code (version 2.5.2) that builds one geometrically valid, watertight, closed, solid body representing the described design.\n\n"
    "The final object must be a single watertight solid: fuse all sub-parts (use combine(), .union(), or other appropraite methods as needed).\n\n"
    "Prioritize modularity, simplicity, correctness, and completeness in syntax and functionality, ensuring the code executes without errors. Ensure correct indentation and no missing parentheses. Always define either 'build()' or 'result = Workplane(...)'.\n\n"
    "Ensure all names are defined and used correctly, and that the code is free of syntax errors. No comments or docstrings in the code.\n\n"
    "Export the final object as a STL file named 'model.stl'."
)

#────────────────────────────────────────────────────────────────────────────────
def generate_cadquery(plan: Dict) -> str:
    """
    Convert build plan JSON → CADQuery code.
    """
    user_prompt = (
        "Build plan JSON:\n```json\n"
        + json.dumps(plan, indent=2)
        + "\n```\nReturn the full CADQuery code."
    )

    resp = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user",   "content": user_prompt},
        ],
        max_completion_tokens=20000,
        #temperature=0.4,
    )
    raw = resp.choices[0].message.content or ""
    code = _strip_fence(raw)     # ← removes ``` blocks *and* leading “python”
    return code, resp.usage        # already clean Python

# app/utils/text.py  – replace old strip_fence
def _strip_fence(text: str) -> str:
    """
    Return the *largest* ```xxx fenced block that contains 'import cadquery'.
    Falls back to the first fenced block or the raw text.
    """
    if "```" not in text:
        return text.strip()

    parts = [p for p in text.split("```") if p.strip()]
    # find all code-looking blocks that mention cadquery
    cad_blocks = [p for p in parts if "import cadquery" in p.lower()]

    block = max(cad_blocks, key=len) if cad_blocks else parts[0]

    block = block.lstrip()
    if block.lower().startswith(("python", "json")):
        block = block.split("\n", 1)[1] if "\n" in block else ""
    return block.strip()

