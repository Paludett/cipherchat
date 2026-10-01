"""
Log de auditoria em JSON, uma linha por evento

who: actor/ip | what: event_type | when: timestamp | where: endpoint/target | result: status

!!! Nunca logar senha, JWT, chave, segredo TOTP, backup code nem conteudo cifrado
"""
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

LOG_FILE = os.getenv("LOG_FILE", "logs/audit.log")

CAMPOS = ("actor", "ip", "endpoint", "target", "status", "alert", "msg_id", "details")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        linha = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "event_type": record.getMessage(),
        }
        for campo in CAMPOS:
            valor = getattr(record, campo, None)
            if valor is not None:
                linha[campo] = valor
        return json.dumps(linha, default=str, ensure_ascii=False)


os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
arquivo = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5)
arquivo.setFormatter(JSONFormatter())
console = logging.StreamHandler()
console.setFormatter(JSONFormatter())

logger = logging.getLogger("audit")
logger.setLevel(logging.INFO)
logger.addHandler(arquivo)
logger.addHandler(console)
