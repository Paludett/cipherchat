"""
Eventos da aplicacao na audit_log (login, MFA, logout) e no log JSON

!!! Nunca passar senha, token ou segredo em details
"""
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.logger import logger
from app.models import AuditLog


def log_event(
    db: Session,
    action: str,
    ip: str | None,
    actor: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    # Commit proprio, o evento fica gravado mesmo que a request termine em erro
    db.add(AuditLog(action=action, actor=actor, ip=ip, details=details))
    db.commit()
    logger.info(action, extra={"actor": actor, "ip": ip, "details": details})
