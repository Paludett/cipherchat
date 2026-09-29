-- pgcrypto: hash de senha (bcrypt via crypt/gen_salt) e funcoes de digest.
-- As tabelas sao criadas pelas migrations do Alembic (backend/alembic).
CREATE EXTENSION IF NOT EXISTS pgcrypto;
