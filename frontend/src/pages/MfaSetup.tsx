import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import { request } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";

type SetupResponse = { secret: string; otpauth_uri: string };
type ActivateResponse = { backup_codes: string[] };

// Fluxo: gerar segredo -> escanear QR e confirmar 1º código -> mostrar backup codes uma vez
export default function MfaSetup() {
  const { token } = useAuth();
  const [setup, setSetup] = useState<SetupResponse | null>(null);
  const [code, setCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function run(action: () => Promise<void>) {
    setError("");
    setLoading(true);
    try {
      await action();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }

  function startSetup() {
    run(async () => {
      setSetup(await request<SetupResponse>("/auth/mfa/setup", { method: "POST", token }));
    });
  }

  function activate(e: FormEvent) {
    e.preventDefault();
    run(async () => {
      const res = await request<ActivateResponse>("/auth/mfa/activate", { method: "POST", body: { code }, token });
      setBackupCodes(res.backup_codes);
    });
  }

  if (backupCodes) {
    return (
      <main className="card">
        <h1>MFA ativado</h1>
        <p className="warning">
          Guarde estes códigos agora, eles não serão mostrados de novo. Cada um serve uma única vez para entrar se você
          perder o celular.
        </p>
        <ul className="backup-codes">
          {backupCodes.map((c) => (
            <li key={c}>
              <code>{c}</code>
            </li>
          ))}
        </ul>
        <Link to="/">Já guardei, voltar ao chat</Link>
      </main>
    );
  }

  if (setup) {
    return (
      <main className="card">
        <h1>Escaneie o QR Code</h1>
        <p>Use Google Authenticator, Authy ou outro app TOTP.</p>
        <QRCodeSVG value={setup.otpauth_uri} size={200} />
        <p>
          Sem câmera? Digite a chave: <code>{setup.secret}</code>
        </p>
        <form onSubmit={activate}>
          <label>
            Código de 6 dígitos do app
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              autoComplete="one-time-code"
              required
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button disabled={loading}>{loading ? "Ativando..." : "Ativar MFA"}</button>
        </form>
      </main>
    );
  }

  return (
    <main className="card">
      <h1>Verificação em 2 etapas</h1>
      <p>Além da senha, o login vai pedir um código do app autenticador no celular.</p>
      {error && <p className="error">{error}</p>}
      <button onClick={startSetup} disabled={loading}>
        {loading ? "Gerando..." : "Gerar QR Code"}
      </button>
      <p>
        <Link to="/">Voltar</Link>
      </p>
    </main>
  );
}
