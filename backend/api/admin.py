"""Admin-only endpoints: weight inspection/override, health."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import ROLE_ADMIN, require_roles
from backend.db.chroma_client import vector_store
from backend.db.postgres import get_session
from backend.ml.risk_model import get_weights
from backend.models.models import RiskWeights
from backend.schemas.schemas import RiskWeightsIn, RiskWeightsOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get(
    "/weights",
    response_model=RiskWeightsOut,
    dependencies=[Depends(require_roles(*ROLE_ADMIN))],
)
async def read_weights(session: AsyncSession = Depends(get_session)):
    a, b, g = await get_weights(session)
    q = await session.execute(select(RiskWeights).where(RiskWeights.id == 1))
    row = q.scalar_one()
    return RiskWeightsOut(alpha=a, beta=b, gamma=g, updated_at=row.updated_at)


@router.put(
    "/weights",
    response_model=RiskWeightsOut,
    dependencies=[Depends(require_roles(*ROLE_ADMIN))],
)
async def set_weights(
    payload: RiskWeightsIn, session: AsyncSession = Depends(get_session)
):
    q = await session.execute(select(RiskWeights).where(RiskWeights.id == 1))
    row = q.scalar_one_or_none()
    if row is None:
        row = RiskWeights(id=1, **payload.model_dump())
        session.add(row)
    else:
        row.alpha = payload.alpha
        row.beta = payload.beta
        row.gamma = payload.gamma
    await session.flush()
    return RiskWeightsOut(
        alpha=row.alpha, beta=row.beta, gamma=row.gamma, updated_at=row.updated_at
    )


@router.get("/health/vector-store")
async def vector_store_health():
    return {"backend": vector_store._backend, "count": vector_store.count()}
