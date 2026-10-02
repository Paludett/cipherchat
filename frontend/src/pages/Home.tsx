import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, request } from "../api";
import { useAuth } from "../auth";
import Chat from "../Chat";
import { fingerprint, formatFingerprint, getOrCreateKeyPair, toBase64 } from "../crypto";
import { friendlyError } from "../errors";

type Me = { id: string; username: string; role: string; mfa_enabled: boolean; fingerprint: string | null };

export default function Home() {
  const { token, logout } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [myFingerprint, setMyFingerprint] = useState("");
  const [error, setError] = useState("");
  const [privateKey, setPrivateKey] = useState<CryptoKey | null>(null);

  // Garante o par local e, se o servidor tem outra publica ou nenhuma, envia a local
  async function setupKeys(me: Me) {
    const { publicKey, privateKey } = await getOrCreateKeyPair(me.id);
    const spki = await crypto.subtle.exportKey("spki", publicKey);
    const fp = await fingerprint(spki);
    if (fp !== me.fingerprint) {
      await request("/keys/me", { method: "PUT", body: { public_key: toBase64(spki) }, token });
    }
    setMyFingerprint(fp);
    setPrivateKey(privateKey);
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

  return (
    <main className="app">
      <header>
        <h1>E2EE Chat</h1>
        {me && <span>Olá, {me.username}!</span>}
        {myFingerprint && (
          <span>
            Sua chave: <code>{formatFingerprint(myFingerprint)}</code>
          </span>
        )}
        {me?.role === "admin" && <Link to="/admin">Admin</Link>}
        {me && !me.mfa_enabled && <Link to="/mfa/setup">Ativar MFA</Link>}
        <button onClick={logout}>Sair</button>
      </header>
      {error && <p className="error">{error}</p>}
      {me && privateKey && <Chat myId={me.id} privateKey={privateKey} />}
    </main>
  );
}
