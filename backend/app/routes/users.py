from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import User
from app.schemas import UserMeOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeOut)
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "username": user.username, "role": user.role,
        "mfa_enabled": user.totp_enabled,
        "fingerprint": user.public_key.fingerprint if user.public_key else None,
    }
