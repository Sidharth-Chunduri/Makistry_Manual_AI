# app/llm/azure_client.py
from functools import lru_cache
from fastapi import HTTPException
from app.core.config import settings

def _fail():
    # Make it explicit to the caller that LLM isn’t configured
    raise HTTPException(status_code=503, detail="Azure OpenAI not configured on this deployment")

@lru_cache(maxsize=1)
def get_azure_openai():
    # Only allow if the required bits are set
    ok = all([
        settings.endpoint,
        settings.api_key,
    ])
    if not ok:
        _fail()

    # Import here so missing deps don’t crash module import
    from openai import AzureOpenAI
    return AzureOpenAI(
        api_key=settings.api_key,
        api_version=(settings.bstorm_api_ver or settings.chat_api_ver or settings.code_api_ver),
        azure_endpoint=settings.endpoint,
    )
