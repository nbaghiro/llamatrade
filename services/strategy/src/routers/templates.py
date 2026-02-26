"""Templates router - pre-built strategy templates."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import (
    StrategyCreate,
    StrategyDetailResponse,
    StrategyType,
    TemplateResponse,
)
from src.services.strategy_service import StrategyService, get_strategy_service
from src.services.template_service import TemplateService, get_template_service

router = APIRouter()


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    strategy_type: StrategyType | None = None,
    difficulty: str | None = Query(
        None, description="Filter by difficulty: beginner, intermediate, advanced"
    ),
    template_service: TemplateService = Depends(get_template_service),
) -> list[TemplateResponse]:
    """List available strategy templates."""
    # template_service.list_templates already returns list[TemplateResponse]
    return await template_service.list_templates(
        strategy_type=strategy_type,
        difficulty=difficulty,
    )


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    template_service: TemplateService = Depends(get_template_service),
) -> TemplateResponse:
    """Get a specific strategy template."""
    # template_service.get_template already returns TemplateResponse | None
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
    symbols: list[str] = Query(None, description="Override symbols (optional)"),
    ctx: TenantContext = Depends(require_auth),
    template_service: TemplateService = Depends(get_template_service),
    strategy_service: StrategyService = Depends(get_strategy_service),
) -> StrategyDetailResponse:
    """Create a new strategy from a template.

    Optionally override the symbols from the template configuration.
    """
    template = await template_service.get_template(template_id=template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    config_sexpr = template.config_sexpr

    # If symbols provided, replace them in the S-expression
    if symbols:
        symbols_str = "[" + " ".join(f'"{s}"' for s in symbols) + "]"
        # Replace the :symbols [...] pattern
        config_sexpr = re.sub(
            r":symbols\s+\[[^\]]*\]",
            f":symbols {symbols_str}",
            config_sexpr,
        )

    # Replace the :name in the S-expression with the user's name
    config_sexpr = re.sub(
        r':name\s+"[^"]*"',
        f':name "{name}"',
        config_sexpr,
    )

    try:
        strategy = await strategy_service.create_strategy(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            data=StrategyCreate(
                name=name,
                description=f"Created from template: {template.name}",
                config_sexpr=config_sexpr,
            ),
        )
        return strategy
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
