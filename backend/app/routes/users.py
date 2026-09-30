from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.models import User
from app.schemas import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    # UserMeOut (com fingerprint) fica para a issue de chaves
    return user
