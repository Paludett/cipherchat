import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, request } from "../api";
import { useAuth } from "../auth";
import Chat from "../Chat";
import { fingerprint, getOrCreateKeyPair, toBase64 } from "../crypto";
import { friendlyError } from "../errors";
import { Button, FormError, KeyGrid, Logo } from "../ui";

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

  const header = (
    <div className="sidebar-header">
      <Logo />
      <Button variant="secondary" size="sm" onClick={logout}>
        Sair
      </Button>
    </div>
  );

  if (!me || !privateKey) {
    return (
      <div className="card-page">
        <main className="card">
          {header}
          {error ? <FormError>{error}</FormError> : <p className="subtitle">Preparando suas chaves...</p>}
        </main>
      </div>
    );
  }

  const meCard = (
    <div className="me-card">
      <div className="me-card-head">
        <div>
          <span className="me-name">Olá, {me.username}</span>
          <span className="me-sub">Sua chave</span>
        </div>
        <div className="me-links">
          {me.role === "admin" && <Link to="/admin">Admin</Link>}
          {!me.mfa_enabled && <Link to="/mfa/setup">Ativar MFA</Link>}
        </div>
      </div>
      {myFingerprint && <KeyGrid fingerprint={myFingerprint} columns={4} />}
    </div>
  );

  // error só é setado antes de privateKey existir, então aparece no estado acima
  return <Chat myId={me.id} privateKey={privateKey} sidebarHeader={header} sidebarFooter={meCard} />;
}
