from fastapi import APIRouter, Request

from app.catalog import Catalog
from app.schemas import CaseSummary

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=list[CaseSummary])
async def list_cases(request: Request) -> list[CaseSummary]:
    catalog: Catalog = request.app.state.catalog
    return await catalog.summaries(request.app.state.engine)
