"""Templates router - pre-built strategy templates."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import StrategyDetailResponse, StrategyType, TemplateResponse
from src.services.strategy_service import StrategyService, get_strategy_service
from src.services.template_service import TemplateService, get_template_service

router = APIRouter()


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    strategy_type: StrategyType | None = None,
    template_service: TemplateService = Depends(get_template_service),
):
    """List available strategy templates."""
    templates = await template_service.list_templates(strategy_type=strategy_type)
    return templates


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    template_service: TemplateService = Depends(get_template_service),
):
    """Get a specific strategy template."""
    template = await template_service.get_template(template_id=template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template


@router.post(
    "/{template_id}/create",
    response_model=StrategyDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_from_template(
    template_id: str,
    name: str = Query(..., min_length=1, max_length=255),
    symbols: list[str] = Query(...),
    ctx: TenantContext = Depends(require_auth),
    template_service: TemplateService = Depends(get_template_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
):
    """Create a new strategy from a template."""
    template = await template_service.get_template(template_id=template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    # Override symbols in the template config
    config = template["config"].model_copy()
    config.symbols = symbols

    strategy = await strategy_service.create_strategy(
        tenant_id=ctx.tenant_id,
        name=name,
        description=f"Created from template: {template['name']}",
        strategy_type=template["strategy_type"],
        config=config,
    )
    return strategy
