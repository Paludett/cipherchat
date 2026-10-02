-- Roles e privilegios (principio do menor privilegio).
--
--   db_admin  dono do schema, unica com DDL (usada so pelas migrations)
--   app_api   role da FastAPI, so DML nas tabelas que precisa
--   auditor   opcional, so le o audit_log
--
-- Este script roda como o superusuario de bootstrap (POSTGRES_USER), so na
-- primeira criacao do volume. Os GRANTs por tabela ficam na migration 0002,
-- porque as tabelas so passam a existir depois do Alembic.

-- Senhas e nome do banco vem das variaveis de ambiente do container (.env)
\getenv db_name POSTGRES_DB
\getenv db_admin_password DB_ADMIN_PASSWORD
\getenv app_api_password APP_API_PASSWORD
\getenv auditor_password AUDITOR_PASSWORD
\getenv app_api_connection_limit APP_API_CONNECTION_LIMIT
\getenv app_api_statement_timeout APP_API_STATEMENT_TIMEOUT

-- Roles, nenhuma é superuser, nenhuma passa por cima de RLS
CREATE ROLE db_admin LOGIN PASSWORD :'db_admin_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

-- CONNECTION LIMIT evita que a API esgote as conexoes do Postgres
CREATE ROLE app_api LOGIN PASSWORD :'app_api_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
    CONNECTION LIMIT :app_api_connection_limit;

ALTER ROLE app_api SET statement_timeout = :'app_api_statement_timeout';

CREATE ROLE auditor LOGIN PASSWORD :'auditor_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
    CONNECTION LIMIT 2;

-- Banco: so as roles acima conectam
REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO db_admin, app_api, auditor;

-- Schema public: db_admin passa a ser o dono, o PUBLIC perde
-- tudo e as demais roles ganham so USAGE para enxergar as tabelas
ALTER SCHEMA public OWNER TO db_admin;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO app_api, auditor;
