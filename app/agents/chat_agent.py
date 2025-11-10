# app/agents/chat_agent.py
import json, textwrap, asyncio
from typing import List, Dict, AsyncGenerator
from openai import AzureOpenAI
from app.core.config import settings
from app.services import storage

_oai = AzureOpenAI(
    azure_endpoint=settings.endpoint,
    api_key=settings.api_key,
    api_version=settings.chat_api_ver,
)
CHAT_MODEL = settings.chat_model        # gpt-4.1 deployment

SYSTEM_TEMPLATE = (
    "You are a helpful and friendly physical product design and engineering assistant. Given a question, summary of changes, and chat history, create an appropriate, relevant, informative, succinct, and technically-sound response.\n"
    "When you reply:\n"
    "1. Always start with answering the questions in an informative, complete, succinct, and contextually aware, with attention to details in the questions and nuances in answers.\n"
    "2. If edits were made, add a 'Edits' section after the answer and include a bullet points list of every edit made verbatim.\n"
    "3. If no edits, don't include the Edits section.\n"
    "Do NOT mention editing code directly, talk about the design in general. Change JSON keys to regular words, like optimal_geometry to optimal geometry, etc.\n"
    "Do NOT give follow up suggestions or questions.\n"
    "Use non-technical language, and avoid jargon unless necessary.\n"
    "In case someone asks what Makistry is, say: 'Makistry is an AI-powered physical product design platform that revolutionizes design and innovation!\n"
    "Do not reveal any details about how Makistry works or any technical details.\n"
)

def _build_messages(user_query: str,
                    summaries: List[str],
                    history: List[Dict]) -> List[Dict]:
    """Assemble the prompt with recent chat history for grounding."""
    user_block = textwrap.dedent(f"""\
        USER_QUERY:
        {user_query}

        EDIT_SUMMARIES:
        {json.dumps(summaries)}
    """)
    msgs = [{"role": "system", "content": SYSTEM_TEMPLATE}]
    for m in history:                         # ground the model
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": user_block})
    return msgs

async def _stream_completion(messages: List[Dict]) -> AsyncGenerator[str, None]: 
    """
    Async generator: yields text chunks for SSE/WebSocket.
    """
    stream = _oai.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        max_completion_tokens=1500,
        temperature=0.4,
        stream=True,
    )
    for chunk in stream:
        for choice in getattr(chunk, 'choices', []):
            content = getattr(choice.delta, 'content', None)
            if content:
                yield content

# high-level wrapper ----------------------------------------------------
async def stream_reply(user_query: str,
                       summaries: List[str],
                       project_id: str) -> AsyncGenerator[str, None]:
    history = storage.last_chat_messages(project_id, limit=20)
    msgs = _build_messages(user_query, summaries, history)
    async for chunk in _stream_completion(msgs):
        yield chunk