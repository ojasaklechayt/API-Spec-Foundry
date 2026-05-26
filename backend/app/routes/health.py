from fastapi import APIRouter

from app.routes.schemas import HealthResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse, operation_id="getHealthz")
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
