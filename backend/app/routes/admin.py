from fastapi import APIRouter, Depends

from app.deps import require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", dependencies=[Depends(require_role("admin"))])
def list_users():
    # Listagem real fica para a issue de admin
    return {"items": [], "total": 0}
