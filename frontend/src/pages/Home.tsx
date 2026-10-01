import { useEffect, useState } from "react";
import { ApiError, WS_URL, request } from "../api";
import { useAuth } from "../auth";
import Contacts from "../Contacts";
import { fingerprint, formatFingerprint, getOrCreateKeyPair, toBase64 } from "../crypto";
import { friendlyError } from "../errors";

type Me = { id: string; username: string; role: string; fingerprint: string | null };

export default function Home() {
  const { token, logout } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [myFingerprint, setMyFingerprint] = useState("");
  const [error, setError] = useState("");
  const [ws, setWs] = useState<WebSocket | null>(null);

  // Garante o par local e, se o servidor tem outra publica ou nenhuma, envia a local
  async function setupKeys(me: Me) {
    const { publicKey } = await getOrCreateKeyPair(me.id);
    const spki = await crypto.subtle.exportKey("spki", publicKey);
    const fp = await fingerprint(spki);
    if (fp !== me.fingerprint) {
      await request("/keys/me", { method: "PUT", body: { public_key: toBase64(spki) }, token });
    }
    setMyFingerprint(fp);
  }

  useEffect(() => {
    request<Me>("/users/me", { token })
      .then((me) => {
        setMe(me);
        return setupKeys(me);
      })
      .catch((err) => {
        // Token expirado (15 min, sem refresh), volta ao login
        if (err instanceof ApiError && err.code === "unauthenticated") logout();
        else setError(friendlyError(err));
      });
  }, []);

  // Conecta no /ws para aparecer online e trocar mensagens, JWT vai no subprotocolo e não na URL
  useEffect(() => {
    const socket = new WebSocket(WS_URL, ["bearer", token!]);
    setWs(socket);
    return () => socket.close();
  }, []);

  return (
    <main className="card">
      <h1>E2EE Chat</h1>
      {error && <p className="error">{error}</p>}
      {me && <p>Olá, {me.username}!</p>}
      {myFingerprint && (
        <p>
          Sua chave: <code>{formatFingerprint(myFingerprint)}</code>
        </p>
      )}
      {me && ws && <Contacts myId={me.id} ws={ws} />}
      <button onClick={logout}>Sair</button>
    </main>
  );
}
