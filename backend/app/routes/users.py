from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import OnlineUserOut, UserMeOut
from app.ws import manager

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeOut)
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "username": user.username, "role": user.role,
        "mfa_enabled": user.totp_enabled,
        "fingerprint": user.public_key.fingerprint if user.public_key else None,
    }


@router.get("/online", response_model=list[OnlineUserOut])
def online(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Descoberta de contatos, quem esta conectado agora, menos o proprio usuario
    ids = [uid for uid in manager.online_ids() if uid != user.id]
    users = db.scalars(select(User).where(User.id.in_(ids))).all()
    return [
        {"id": u.id, "username": u.username,
         "fingerprint": u.public_key.fingerprint if u.public_key else None}
        for u in users
    ]
