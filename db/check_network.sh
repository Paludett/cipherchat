# Evidencia de que o Postgres so e acessivel pela rede interna do compose.
# Uso (com o compose rodando): ./db/check_network.sh

cd "$(dirname "$0")/.."

ok()    { echo "  OK     - $1"; }
falha() { echo "  FALHOU - $1"; FALHAS=1; }
FALHAS=0

DB_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(docker compose ps -q db)")
echo "IP do banco na rede interna: $DB_IP"
echo

echo "1) De dentro da rede interna, como app_api (scram-sha-256)"
if docker compose exec -T db sh -c 'PGPASSWORD=$APP_API_PASSWORD psql -h db -U app_api -d $POSTGRES_DB -tAc "select 1"' > /dev/null; then
  ok "conexao aceita"
else
  falha "conexao deveria ser aceita"
fi

echo "2) Do host, pela porta 5432"
if docker port "$(docker compose ps -q db)" 5432 > /dev/null 2>&1; then
  falha "porta 5432 do banco esta publicada no host"
else
  ok "porta 5432 do banco nao publicada no host"
fi

echo "3) De um container fora da rede do compose"
if docker run --rm postgres:16-alpine pg_isready -h "$DB_IP" -t 3 > /dev/null; then
  falha "banco alcancavel de outra rede docker"
else
  ok "sem resposta (redes isoladas)"
fi

echo
if [ "$FALHAS" -eq 0 ]; then echo "Tudo certo"; else echo "Ha falhas"; exit 1; fi
