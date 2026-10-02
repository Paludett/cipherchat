from fastapi import APIRouter, Depends

from app.deps import paginar, require_role

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", dependencies=[Depends(require_role("admin"))])
def list_users(pagina: dict = Depends(paginar)):
    return {"items": [], "total": 0}
