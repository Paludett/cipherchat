FROM postgres:16-alpine

ENV POSTGRES_INITDB_ARGS="--auth-host=scram-sha-256 --auth-local=scram-sha-256"

COPY pg_hba.conf /etc/postgresql/pg_hba.conf
COPY init/ /docker-entrypoint-initdb.d/
COPY demo_app_api.sql /demo_app_api.sql

CMD ["postgres", "-c", "listen_addresses=*", "-c", "hba_file=/etc/postgresql/pg_hba.conf"]
