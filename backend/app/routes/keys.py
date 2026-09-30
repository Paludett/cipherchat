"""
Chaves publicas RSA dos usuarios (BOLA)

PUT /keys/me: o user_id vem so do token, nunca do body/URL, e nao existe rota
que altere a chave de outro usuario.
GET /keys/{user_id}: qualquer autenticado le a chave publica de qualquer um
"""
import base64
import binascii
import hashlib
import uuid

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.audit import log_event
from app.db import get_db
from app.deps import get_current_user
from app.errors import ApiError
from app.models import PublicKey, User
from app.schemas import FingerprintOut, PublicKeyOut, PublicKeyUpdate

router = APIRouter(prefix="/keys", tags=["keys"])


def fingerprint_rsa_2048(public_key_b64: str) -> str:
    # Aceita so base64 de SPKI DER com RSA de 2048 bits
    try:
        der = base64.b64decode(public_key_b64, validate=True)
        chave = load_der_public_key(der)
    except (binascii.Error, ValueError):
        chave = None
    if not isinstance(chave, RSAPublicKey) or chave.key_size != 2048:
        raise ApiError(400, "validation_error", "Chave pública inválida.")
    return hashlib.sha256(der).hexdigest()


@router.put("/me", response_model=FingerprintOut)
def publicar_chave(
    body: PublicKeyUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fingerprint = fingerprint_rsa_2048(body.public_key)
    antiga = user.public_key.fingerprint if user.public_key else None
    user.public_key = PublicKey(public_key=body.public_key, fingerprint=fingerprint)
    db.commit()
    ip = request.client.host if request.client else None
    log_event(db, "key_changed", ip, actor=user.id,
              details={"old_fingerprint": antiga, "new_fingerprint": fingerprint})
    return {"fingerprint": fingerprint}


@router.get("/{user_id}", response_model=PublicKeyOut, dependencies=[Depends(get_current_user)])
def ler_chave(user_id: uuid.UUID, db: Session = Depends(get_db)):
    chave = db.get(PublicKey, user_id)
    if chave is None:
        raise ApiError(404, "not_found", "Chave não encontrada.")
    return {"user_id": chave.user_id, "username": chave.user.username,
            "public_key": chave.public_key, "fingerprint": chave.fingerprint}
