import { useEffect, useRef, useState } from "react";
import { WS_URL } from "./api";
import { useAuth } from "./auth";

const RETRY_MS = 2000;
const REPLACED = 1000; // servidor fecha a conexão antiga quando o mesmo usuário conecta de novo
const UNAUTHORIZED = 1008; 

export type SocketStatus = "conectando" | "conectado" | "reconectando" | "aberto em outra aba";

// Mantém o /ws aberto e reconecta sozinho quando cai.
export function useSocket(onMessage: (data: any) => void) {
  const { token, logout } = useAuth();
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [status, setStatus] = useState<SocketStatus>("conectando");

  // Sempre chama o handler mais recente, sem recriar a conexão a cada render
  const handler = useRef(onMessage);
  handler.current = onMessage;

  useEffect(() => {
    let ws: WebSocket;
    let retry: ReturnType<typeof setTimeout>;
    let stopped = false;

    function connect() {
      // JWT vai no subprotocolo e não na URL
      ws = new WebSocket(WS_URL, ["bearer", token!]);
      ws.onopen = () => {
        setSocket(ws);
        setStatus("conectado");
      };
      ws.onmessage = (e) => handler.current(JSON.parse(e.data));
      ws.onclose = (e) => {
        setSocket(null);
        if (stopped) return;
        if (e.code === UNAUTHORIZED && e.reason !== "rate_limited") return logout();
        if (e.code === REPLACED) return setStatus("aberto em outra aba");
        setStatus("reconectando");
        retry = setTimeout(connect, RETRY_MS);
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      ws.close();
    };
  }, [token]);

  return { socket, status };
}
