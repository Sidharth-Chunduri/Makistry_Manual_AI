# app/routes/chat_history.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from google.cloud.firestore import Query as FSQuery
from app.services.auth import get_current_user
from app.services.storage_gcp import C_CHAT

router = APIRouter(tags=["chat"])

@router.get("/chat/history", response_model=List[dict])
def get_chat_history(
    project_id: str = Query(...),
    user=Depends(get_current_user),
):
    # TODO: enforce that user.sub === owner of project_id
    snaps = (
        C_CHAT.where("projectID", "==", project_id)
              .order_by("ts", direction=FSQuery.DESCENDING)
              .get()
    )
    # return oldest→newest
    msgs = [{"id": s.id, **s.to_dict()} for s in snaps]
    return list(reversed(msgs))