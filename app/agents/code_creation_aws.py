"""
Generate CADQuery code from brainstorm JSON using AWS Bedrock
(Anthropic Claude Sonnet 4).
"""

from __future__ import annotations
import json, logging
from typing import Dict

import boto3                         # NEW
from botocore.exceptions import NoCredentialsError, ClientError
from app.core.config import settings

# ── warm Bedrock client ──────────────────────────────────────────────
_bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name=settings.aws_region,
)

logger = logging.getLogger(__name__)

# Initialize Bedrock client with proper error handling
def _get_bedrock_client():
    """Get Bedrock client with proper configuration"""
    try:
        return boto3.client(
            service_name="bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
    except Exception as e:
        logger.error(f"Failed to initialize Bedrock client: {e}")
        raise

MODEL_ID = getattr(settings, 'sonnet_model_id', "us.anthropic.claude-sonnet-4-20250514-v1:0") # e.g. "anthropic.claude-sonnet-4-20250514-v1:0"

_SYSTEM_MSG = (
    "Given detailed design information, return ONLY relevant, comprehensive, and "
    "working CADQuery-Python code (v2.5.2) that builds one geometrically valid, "
    "watertight, closed, solid body that accurately reflects the described design.\n"
    "Ensure the code accurately reflects and includes all features, functionalities, components, and geometries outlined in the brainstorm.\n"
    "**ALWAYS** assign the final object to 'result' (result = <solid or assembly>)\n"
    "Ensure the assembly is correct and all the sub-components are positioned, oriented, aligned correctly, and are all physically touching.\n"
    "After boolean operations, ensure the 'result' contains all the sub-components.\n"
    "Do NOT set color in the script, it is handled later.\n Ensure correct operation ordering and stable selection for filleting and chamfering.\n"
    "Keep the code modular, syntactically correct, and **do not add any comments or docstrings**. Do NOT export the design, the sandbox handles it."
)

def generate_cadquery(plan: Dict) -> tuple[str, Dict]:
    """
    Convert build-plan JSON ➜ CADQuery code using Claude Sonnet 4.
    Returns (clean_code, usage_dict).
    """
    user_prompt = (
        "Brainstorm JSON:\n```json\n"
        + json.dumps(plan, indent=2)
        + "\n```\nReturn the full CADQuery code."
    )

    # Bedrock “native” Claude JSON body
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": _SYSTEM_MSG, 
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 16000,          # Sonnet 4 allows up to ~16 k output
        "temperature": 0.2,
    }

    try:
        _bedrock = _get_bedrock_client()
        
        logger.info(f"Calling Bedrock with model: {MODEL_ID}")
        
        response = _bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        
        logger.info("Bedrock call successful")

    except NoCredentialsError as e:
        logger.exception("Bedrock credentials not found")
        raise RuntimeError("Bedrock credentials not found. Set AWS_ACCESS_KEY_ID/SECRET (and SESSION_TOKEN if using STS).") from e
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        logger.exception(f"Bedrock ClientError: {error_code} - {error_message}")
        
        # Handle specific errors
        if error_code == 'ValidationException':
            raise RuntimeError(f"Bedrock validation error: {error_message}. Check your model ID and request format.") from e
        elif error_code == 'AccessDeniedException':
            raise RuntimeError(f"Bedrock access denied: {error_message}. Check your IAM permissions and model access.") from e
        elif error_code == 'ResourceNotFoundException':
            raise RuntimeError(f"Bedrock model not found: {error_message}. Check if the model is available in your region.") from e
        else:
            raise RuntimeError(f"Bedrock client error ({error_code}): {error_message}") from e
    except Exception as e:
        logger.exception(f"Unexpected error calling Bedrock: {e}")
        raise RuntimeError(f"Unexpected Bedrock error: {str(e)}") from e


    try:
        # Parse response
        response_body = response["body"].read()
        model_response = json.loads(response_body)
        
        if "content" not in model_response or not model_response["content"]:
            raise RuntimeError("Empty response from Bedrock")
            
        raw = model_response["content"][0]["text"]
        code = _strip_fence(raw)
        usage = model_response.get("usage", {})
        
        logger.info(f"Generated {len(code)} characters of CADQuery code")
        return code, usage
        
    except (json.JSONDecodeError, KeyError) as e:
        logger.exception(f"Failed to parse Bedrock response: {e}")
        raise RuntimeError(f"Failed to parse Bedrock response: {str(e)}") from e


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