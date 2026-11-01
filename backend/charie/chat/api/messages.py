"""Message addresses: Finish now (P10.1). The stream lands in P10.2."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from charie.chat import chat_store
from charie.chat.analyst.runner import request_finish
from charie.shared.db import get_session
from charie.shared.errors import ApiError

messages_router = APIRouter()


@messages_router.post("/api/messages/{message_id}/finish")
def finish_now(message_id: int, session: Session = Depends(get_session)) -> dict:
    """Stop a running question at its next pause. A finished one refuses."""
    message = chat_store.get_message(session, message_id)
    if message.role != "assistant":
        raise ApiError(404, "not_found", "That message doesn't exist.")
    if message.status not in ("thinking", "writing"):
        raise ApiError(409, "not_running", "This question has already finished.")
    request_finish(message_id)
    return {"finished": True, "message_id": message_id}
