# app/agents/brainstorm.py
"""
Brainstorm agent for Makistry.
Calls an gpt-4.1 deployment on Azure AI Foundry and returns a structured brainstorm JSON.
"""

import json, logging
from typing import Dict
from openai import AzureOpenAI
from openai.types.chat import ChatCompletionMessageParam
from app.core.config import settings

_client = AzureOpenAI(
    api_version=settings.bstorm_api_ver,
    azure_endpoint=settings.endpoint,
    api_key=settings.api_key,
)


SCHEMA = """
Return ONLY valid JSON with keys:
- project_name: string (≤2 words, concise, and descriptive)
- key_features: list of distinct product features
- key_functionalities: list of capabilities aligned with user needs
- design_components: complete list of physical/mechanical design components enabling features and functionalities
- optimal_geometry: key geometric parameters and dimensions
- design_one_liner: descriptive product summary (≤20 words)
"""


def heavy_brainstorm(user_prompt: str) -> Dict:
    messages: list[ChatCompletionMessageParam] = [
        {
            "role": "system",
            "content": (
                "Role: You are a helpful and inventive physical product design brainstorming assistant.\n"
                "Goal: Convert a product idea or problem statement into structured, comprehensive, technically sound, and creative design information, requirements, and constraints.\n"
                "Consider design intent, use cases, target users, existing solutions, and engineering feasibility silently. Only include features, functionalities, and components that direct relate to the idea and solve the problem, do not add extra information.\n"
                "Ensure all responses are succinct, relevant, practical, and clear using a formal yet approachable tone with non-technical language. If input lacks detail, make relevant, informed, and feasible guesses and informed assumption with caution.\n"
                "Ensure all values are concrete, not ranges. Use provided values whenever possible, otherwise use your best judgement. Always include approprite units. Ensure designs are simple yet functional and detailed.\n"
                "Ensure the geometric information is comprehensive, technically correct, feasible, and based on engineering principles for all appropriate components.\n"
                + SCHEMA
            ),
        },
        {"role": "user", "content": user_prompt},
    ]
    resp = _client.chat.completions.create(
        model=settings.bstorm_model,
        messages=messages,
        max_completion_tokens=2000,
        #response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content

    if not content.startswith("{"):
        content = strip_fence(content)

    try:
        return json.loads(content), resp.usage
    except json.JSONDecodeError as exc:
        logging.exception("Heavy-brainstorm returned invalid JSON")
        raise RuntimeError(f"Invalid JSON from model:\n{content}") from exc

if __name__ == "__main__":
    import json, sys
    prompt = " ".join(sys.argv[1:]) or "Portable espresso maker for camping."
    print(json.dumps(heavy_brainstorm(prompt), indent=2))

def strip_fence(text: str) -> str:
    """Remove ```json / ```python fences + leading language tag."""
    if "```" in text:
        # keep the block that actually contains a JSON brace
        text = next((b for b in text.split("```") if "{" in b), text)
    text = text.lstrip()
    if text.lower().startswith(("json", "python")):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text.strip()