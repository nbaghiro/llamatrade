"""Authentication router - login, register, token refresh."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from src.services.auth_service import AuthService, get_auth_service
from src.services.user_service import UserService, get_user_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Register a new user and tenant."""
    try:
        user = await auth_service.register(
            tenant_name=request.tenant_name,
            email=request.email,
            password=request.password,
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Registration failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Authenticate user and return tokens."""
    tokens = await auth_service.login(email=request.email, password=request.password)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """Refresh access token using refresh token."""
    tokens = await auth_service.refresh_token(request.refresh_token)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    return tokens


@router.post("/logout")
async def logout(
    ctx: TenantContext = Depends(require_auth),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Logout user and invalidate tokens."""
    await auth_service.logout(user_id=ctx.user_id)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    ctx: TenantContext = Depends(require_auth),
    user_service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Get current authenticated user."""
    user = await user_service.get_user(user_id=ctx.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    ctx: TenantContext = Depends(require_auth),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Change user password."""
    success = await auth_service.change_password(
        user_id=ctx.user_id,
        current_password=request.current_password,
        new_password=request.new_password,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    return {"message": "Password changed successfully"}
