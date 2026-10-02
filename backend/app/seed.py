"""
Cria o admin inicial, unico jeito de existir um admin sem outro admin promover
"""
import os
import sys

from sqlalchemy import select, update

from app import security
from app.db import SessionLocal
from app.models import User


def main() -> None:
    username = os.environ["ADMIN_USERNAME"]
    password = os.environ["ADMIN_PASSWORD"]

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.username == username)) is not None:
            print(f"admin '{username}' ja existe, nada feito")
            return
        try:
            # Mesma validacao e hash do /auth/register
            user_id = security.create_user(db, username, password)
        except ValueError:
            sys.exit(f"senha fraca, minimo de {security.MIN_PASSWORD_LENGTH} caracteres")
        db.execute(update(User).where(User.id == user_id).values(role="admin"))
        db.commit()
        print(f"admin '{username}' criado")


if __name__ == "__main__":
    main()
