import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";
import { request } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";
import { Button, CardPage, FormError, OtpInput, PhoneIcon } from "../ui";

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
      <CardPage step={2} wide>
        <div className="page-head">
          <h1 className="title-page">MFA ativado</h1>
          <p className="subtitle">Agora o login também pede o código do app autenticador.</p>
        </div>
        <p className="notice">
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
        <div className="card-footer">
          <Link to="/">Já guardei, voltar ao chat</Link>
        </div>
      </CardPage>
    );
  }

  if (setup) {
    return (
      <CardPage step={2} wide>
        <div className="page-head">
          <h1 className="title-page">Escaneie o QR Code</h1>
          <p className="subtitle">Use Google Authenticator, Authy ou outro app TOTP.</p>
        </div>
        <div className="qr-row">
          <div className="qr">
            <QRCodeSVG value={setup.otpauth_uri} size={176} />
          </div>
          <div className="field">
            <span className="field-label">Sem câmera? Digite a chave:</span>
            <code className="secret">{setup.secret.match(/.{1,4}/g)!.join(" ")}</code>
          </div>
        </div>
        <div className="divider" />
        <form onSubmit={activate}>
          <div className="field">
            <span className="field-label">Código de 6 dígitos do app</span>
            <div className="otp-row">
              <OtpInput
                aria-label="Código de 6 dígitos do app"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
                required
              />
              <Button disabled={loading}>{loading ? "Ativando..." : "Ativar MFA"}</Button>
            </div>
            {error && <FormError>{error}</FormError>}
          </div>
        </form>
        <div className="card-footer">
          <Link to="/">Voltar</Link>
        </div>
      </CardPage>
    );
  }

  return (
    <CardPage step={1}>
      <div className="icon-tile">
        <PhoneIcon />
      </div>
      <div className="page-head">
        <h1 className="title-page">Verificação em 2 etapas</h1>
        <p className="subtitle">Além da senha, o login vai pedir um código do app autenticador no celular.</p>
      </div>
      {error && <FormError>{error}</FormError>}
      <div className="card-footer">
        <Link to="/">Voltar</Link>
        <Button onClick={startSetup} disabled={loading}>
          {loading ? "Gerando..." : "Gerar QR Code"}
        </Button>
      </div>
    </CardPage>
  );
}
