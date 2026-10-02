import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";
import { AuthShell, Button, CardPage, FormError, Input, OtpInput, PhoneIcon } from "../ui";

export default function Login() {
  const { login, verifyMfa, recoverMfa } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // Preenchido quando a senha confere e a conta tem MFA, liga o 2º passo
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [useBackup, setUseBackup] = useState(false);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!mfaToken) {
      const pending = await login(username, password);
      if (pending) setMfaToken(pending);
      else navigate("/");
    } else if (useBackup) {
      await recoverMfa(mfaToken, code.trim().toLowerCase());
      // Recover desliga o MFA, já leva para configurar de novo
      navigate("/mfa/setup");
    } else {
      await verifyMfa(mfaToken, code);
      navigate("/");
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await submit();
    } catch (err) {
      // Token parcial expirou ou já foi usado, recomeça pela senha
      if (err instanceof ApiError && err.code === "unauthenticated") setMfaToken(null);
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }

  function toggleBackup() {
    setUseBackup(!useBackup);
    setCode("");
    setError("");
  }

  if (mfaToken) {
    return (
      <CardPage>
        <div className="icon-tile">
          <PhoneIcon />
        </div>
        <div className="page-head">
          <h1 className="title-page">Verificação em 2 etapas</h1>
          <p className="subtitle">
            {useBackup ? "Digite um dos backup codes que você guardou." : "Digite o código de 6 dígitos do app autenticador."}
          </p>
        </div>
        <form onSubmit={handleSubmit}>
          {useBackup ? (
            <Input
              label="Backup code"
              className="mono"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="xxxxx-xxxxx"
              invalid={!!error}
              required
            />
          ) : (
            <div className="field">
              <span className="field-label">Código do app autenticador</span>
              <OtpInput
                aria-label="Código do app autenticador"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
                autoFocus
                required
              />
            </div>
          )}
          {error && <FormError>{error}</FormError>}
          <Button disabled={loading}>{loading ? "Verificando..." : "Verificar"}</Button>
        </form>
        <div className="card-footer">
          <button type="button" className="link-button" onClick={toggleBackup}>
            {useBackup ? "Usar código do app" : "Perdeu o celular? Usar backup code"}
          </button>
        </div>
      </CardPage>
    );
  }

  return (
    <AuthShell
      hero="Só você e quem recebe leem a conversa."
      text="As mensagens são cifradas no seu dispositivo antes de sair. O servidor só repassa texto ilegível."
      hex={["2ed1 e230 d808 5c7f", "c581 6a96 c148 a7d6"]}
    >
      <div className="page-head">
        <h1 className="title-auth">Entrar</h1>
        <p className="subtitle">Use seu usuário e senha.</p>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="fields">
          <Input
            label="Usuário"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            invalid={!!error}
            required
          />
          <Input
            label="Senha"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            invalid={!!error}
            required
          />
          {error && <FormError>{error}</FormError>}
        </div>
        <Button disabled={loading}>{loading ? "Entrando..." : "Entrar"}</Button>
      </form>
      <p className="auth-switch">
        Não tem conta? <Link to="/register">Criar conta</Link>
      </p>
    </AuthShell>
  );
}
