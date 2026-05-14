"""Analyst feedback endpoints."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.feedback_agent import feedback_agent
from backend.core.security import ROLE_ANALYST, get_current_user, require_roles
from backend.db.postgres import get_session
from backend.models.models import User
from backend.schemas.schemas import FeedbackIn, FeedbackOut

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post(
    "/{incident_id}",
    response_model=FeedbackOut,
    dependencies=[Depends(require_roles(*ROLE_ANALYST))],
)
async def submit_feedback(
    incident_id: uuid.UUID,
    payload: FeedbackIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    fb = await feedback_agent.handle(
        incident_id=incident_id,
        verdict=payload.verdict,
        notes=payload.notes,
        analyst=user,
        session=session,
    )
    return fb
