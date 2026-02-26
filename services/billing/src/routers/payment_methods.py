"""Payment methods router - card and payment method management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import PaymentMethodCreate, PaymentMethodResponse, SetupIntentResponse
from src.services.payment_method_service import PaymentMethodService, get_payment_method_service

router = APIRouter()


@router.post("/setup-intent", response_model=SetupIntentResponse)
async def create_setup_intent(
    ctx: TenantContext = Depends(require_auth),
    payment_service: PaymentMethodService = Depends(get_payment_method_service),
) -> SetupIntentResponse:
    """Create a SetupIntent for collecting card details.

    The client_secret should be used with Stripe.js confirmCardSetup()
    to securely collect and save card details.
    """
    try:
        return await payment_service.create_setup_intent(
            tenant_id=ctx.tenant_id,
            email=ctx.email,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("", response_model=list[PaymentMethodResponse])
async def list_payment_methods(
    ctx: TenantContext = Depends(require_auth),
    payment_service: PaymentMethodService = Depends(get_payment_method_service),
) -> list[PaymentMethodResponse]:
    """List all saved payment methods for the tenant."""
    return await payment_service.list_payment_methods(ctx.tenant_id)


@router.post("", response_model=PaymentMethodResponse, status_code=status.HTTP_201_CREATED)
async def attach_payment_method(
    request: PaymentMethodCreate,
    ctx: TenantContext = Depends(require_auth),
    payment_service: PaymentMethodService = Depends(get_payment_method_service),
) -> PaymentMethodResponse:
    """Attach a new payment method.

    The payment_method_id should be obtained from Stripe.js after
    confirming a SetupIntent with confirmCardSetup().
    """
    try:
        return await payment_service.attach_payment_method(
            tenant_id=ctx.tenant_id,
            email=ctx.email,
            payment_method_id=request.payment_method_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{payment_method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_method(
    payment_method_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    payment_service: PaymentMethodService = Depends(get_payment_method_service),
) -> None:
    """Delete a payment method."""
    try:
        deleted = await payment_service.delete_payment_method(
            tenant_id=ctx.tenant_id,
            payment_method_id=payment_method_id,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment method not found",
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.put("/{payment_method_id}/default", response_model=PaymentMethodResponse)
async def set_default_payment_method(
    payment_method_id: UUID,
    ctx: TenantContext = Depends(require_auth),
    payment_service: PaymentMethodService = Depends(get_payment_method_service),
) -> PaymentMethodResponse:
    """Set a payment method as the default."""
    try:
        return await payment_service.set_default_payment_method(
            tenant_id=ctx.tenant_id,
            payment_method_id=payment_method_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
