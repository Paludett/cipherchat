"""
Gestao de usuarios pelo admin

Toda rota exige require_role("admin") e grava a acao na audit_log com o admin
como actor. O trigger de users ja guarda o antes/depois, aqui fica quem fez
O admin nao altera nem remove a si mesmo, assim sempre sobra pelo menos um admin
"""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import paginar, require_role
from app.errors import ApiError
from app.models import User
from app.schemas import AdminUserPage, AdminUserUpdate, AdminUserUpdatedOut
from app.ws import manager

router = APIRouter(prefix="/admin", tags=["admin"])


def buscar_alvo(db: Session, admin: User, user_id: uuid.UUID, ip: str | None) -> User:
    if user_id == admin.id:
        log_event(db, "admin_modify_self_denied", ip, actor=admin.id)
        raise ApiError(403, "cannot_modify_self", "Você não pode alterar nem remover a si mesmo.")
    alvo = db.get(User, user_id)
    if alvo is None:
        raise ApiError(404, "not_found", "Usuário não encontrado.")
    return alvo


@router.get("/users", response_model=AdminUserPage)
def list_users(
    pagina: dict = Depends(paginar),
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    users = db.scalars(
        select(User).order_by(User.created_at, User.id).limit(pagina["limit"]).offset(pagina["offset"])
    ).all()
    total = db.scalar(select(func.count()).select_from(User))
    return {"items": users, "total": total}


@router.patch("/users/{user_id}", response_model=AdminUserUpdatedOut)
def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    request: Request,
    tasks: BackgroundTasks,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    alvo = buscar_alvo(db, admin, user_id, ip)
    mudancas = body.model_dump(exclude_none=True)
    for campo, valor in mudancas.items():
        setattr(alvo, campo, valor)
    db.commit()

    log_event(db, "admin_user_updated", ip, actor=admin.id,
              details={"target": str(alvo.id), "changes": mudancas})
    if mudancas.get("is_active") is False:
        tasks.add_task(manager.derrubar, alvo.id)
    return alvo


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: uuid.UUID,
    request: Request,
    tasks: BackgroundTasks,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    ip = request.client.host if request.client else None
    alvo = buscar_alvo(db, admin, user_id, ip)
    username = alvo.username
    db.delete(alvo)
    db.commit()

    log_event(db, "admin_user_deleted", ip, actor=admin.id,
              details={"target": str(user_id), "username": username})
    tasks.add_task(manager.derrubar, user_id)
    return Response(status_code=204)
