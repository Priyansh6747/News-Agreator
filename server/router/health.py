from __future__ import annotations

from fastapi import APIRouter, Response

from router.deps import readiness

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response) -> dict[str, object]:
    info = readiness()
    if not info["backends"]:
        response.status_code = 503
    return info
