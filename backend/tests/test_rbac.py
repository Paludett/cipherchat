import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import text

from app import tokens
from tests.test_auth import client, db, login, user  # noqa: F401 (fixtures)


def forjar_token(user_id, **alterar) -> str:
    # Token de acesso valido, com os claims sobrescritos pelo teste
    agora = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id), "role": "user", "scope": "access",
        "iss": tokens.JWT_ISSUER, "aud": tokens.JWT_AUDIENCE,
        "iat": agora, "exp": agora + timedelta(minutes=5), "jti": str(uuid.uuid4()),
    }
    claims.update(alterar)
    return jwt.encode(claims, tokens.JWT_SECRET, algorithm=tokens.JWT_ALGORITHM)


def get(rota: str, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(rota, headers=headers)


def assert_401(resp):
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"


def test_sem_token_devolve_401():
    assert_401(get("/users/me"))


def test_token_valido_acessa_rota_de_user(user):
    _, user_id = user
    resp = get("/users/me", forjar_token(user_id))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(user_id)


def test_token_de_user_em_rota_de_admin_devolve_403(user):
    _, user_id = user
    resp = get("/admin/users", forjar_token(user_id))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_admin_acessa_rota_de_admin(db, user):
    username, user_id = user
    db.execute(text("UPDATE users SET role = 'admin' WHERE id = :id"), {"id": user_id})
    db.commit()

    token = login(username).json()["access_token"]
    assert get("/admin/users", token).status_code == 200


def test_token_expirado_devolve_401(user):
    _, user_id = user
    expirado = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert_401(get("/users/me", forjar_token(user_id, exp=expirado)))


def test_issuer_errado_devolve_401(user):
    _, user_id = user
    assert_401(get("/users/me", forjar_token(user_id, iss="outro-emissor")))


def test_audience_errada_devolve_401(user):
    _, user_id = user
    assert_401(get("/users/me", forjar_token(user_id, aud="outra-audiencia")))


def test_token_adulterado_devolve_401(user):
    _, user_id = user
    header, _, assinatura = forjar_token(user_id).split(".")
    # Troca o payload para role=admin e mantem a assinatura original
    payload = {"sub": str(user_id), "role": "admin", "scope": "access",
               "iss": tokens.JWT_ISSUER, "aud": tokens.JWT_AUDIENCE,
               "exp": 9999999999}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    assert_401(get("/admin/users", f"{header}.{payload_b64}.{assinatura}"))
