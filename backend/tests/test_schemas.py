import uuid

import pytest
from pydantic import ValidationError

from app import schemas
from app.models import User

VALIDO = {"username": "alice_01", "password": "senha-forte-123"}


def test_registro_valido_passa():
    user = schemas.UserCreate(**VALIDO)
    assert user.username == "alice_01"


@pytest.mark.parametrize(
    "extra",
    [{"role": "admin"}, {"is_active": True}, {"totp_secret": "x"}, {"totp_enabled": True}],
)
def test_registro_rejeita_campo_extra(extra):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        schemas.UserCreate(**VALIDO, **extra)


@pytest.mark.parametrize("username", ["ab", "a" * 33, "com espaco", "joão", "a-b", "a;drop"])
def test_username_invalido(username):
    with pytest.raises(ValidationError):
        schemas.UserCreate(username=username, password="senha-forte-123")


def test_senha_acima_de_72_rejeitada():
    with pytest.raises(ValidationError):
        schemas.UserCreate(username="alice", password="a" * 73)


def test_todo_schema_de_entrada_proibe_extra():
    for schema in schemas.Entrada.__subclasses__():
        assert schema.model_config["extra"] == "forbid", schema.__name__


def test_nenhuma_saida_tem_campo_sensivel():
    sensiveis = {"password", "password_hash", "totp_secret"}
    for schema in schemas.Saida.__subclasses__():
        assert not sensiveis & schema.model_fields.keys(), schema.__name__


def test_saida_do_model_orm_nao_vaza_segredo():
    user = User(
        id=uuid.uuid4(),
        username="alice",
        password_hash="$2a$12$hash",
        role="user",
        is_active=True,
        totp_secret=b"cifrado",
        totp_enabled=False,
    )
    corpo = schemas.UserOut.model_validate(user).model_dump()
    assert corpo.keys() == {"id", "username", "role"}
