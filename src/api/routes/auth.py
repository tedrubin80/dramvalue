"""
Authentication endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.security import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_password_reset_token,
)
from src.db.session import get_db
from src.models.user import User

router = APIRouter()


# =============================================================================
# Request/Response Schemas
# =============================================================================


class UserRegister(BaseModel):
    """User registration request."""
    display_name: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Authentication token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user information."""
    id: int
    display_name: str
    email_verified: bool
    trust_score: float

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Register a new pseudonymous account.

    - Display name is public
    - Email is admin-only (for verification)
    - Returns user info (no tokens until email verified for submissions)
    """
    # Check if email exists
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Check if display name exists
    result = await db.execute(select(User).where(User.display_name == data.display_name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Display name already taken",
        )

    # Create user
    user = User(
        display_name=data.display_name,
        email=data.email,
        hashed_password=get_password_hash(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Send verification email (non-blocking — failure doesn't block registration)
    try:
        from src.services.email_service import send_verification_email
        import asyncio
        verification_token = create_email_verification_token(data.email)
        base_url = str(settings.cors_origins.split(",")[0]).rstrip("/") if settings.cors_origins else "https://dramvalue.com"
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, send_verification_email, data.email, verification_token, user.display_name, base_url)
    except Exception:
        pass  # Registration succeeds even if email fails

    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Authenticate and receive tokens.
    Also sets HTTP-only cookie for server-side auth.
    """
    settings = get_settings()

    # Find user
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is banned: {user.ban_reason or 'No reason provided'}",
        )

    # Generate tokens
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # Set HTTP-only cookie for server-side auth
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=not settings.is_development,  # Secure in production
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/logout")
async def logout(response: Response):
    """
    Logout by clearing the auth cookie.
    """
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}


@router.get("/logout")
async def logout_redirect():
    """
    Logout and redirect to home (for form/link logout).
    """
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="access_token")
    return response


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    """
    Verify email address with token from verification email.
    """
    from src.core.security import verify_email_token

    email = verify_email_token(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.email_verified:
        return MessageResponse(message="Email already verified")

    user.email_verified = True
    await db.commit()

    return MessageResponse(message="Email verified successfully")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Send a password reset email.

    Always returns success to prevent email enumeration.
    """
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user and user.is_active and not user.is_banned:
        try:
            from src.services.email_service import send_password_reset_email
            import asyncio
            settings = get_settings()
            base_url = str(settings.cors_origins.split(",")[0]).rstrip("/") if settings.cors_origins else "https://dramvalue.com"
            token = create_password_reset_token(data.email)
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, send_password_reset_email, data.email, token, user.display_name, base_url)
        except Exception:
            pass  # Don't expose failures

    return MessageResponse(message="If that email is registered, a reset link is on its way.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password using a valid reset token."""
    email = verify_password_reset_token(data.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token. Please request a new one.",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.hashed_password = get_password_hash(data.new_password)
    await db.commit()

    return MessageResponse(message="Password updated. You can now log in.")
