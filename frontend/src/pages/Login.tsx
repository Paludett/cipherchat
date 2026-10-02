import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";

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
      <main className="card">
        <h1>Verificação em 2 etapas</h1>
        <form onSubmit={handleSubmit}>
          {useBackup ? (
            <label>
              Backup code
              <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="xxxxx-xxxxx" required />
            </label>
          ) : (
            <label>
              Código do app autenticador
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
          )}
          {error && <p className="error">{error}</p>}
          <button disabled={loading}>{loading ? "Verificando..." : "Verificar"}</button>
        </form>
        <button type="button" className="link" onClick={toggleBackup}>
          {useBackup ? "Usar código do app" : "Perdeu o celular? Usar backup code"}
        </button>
      </main>
    );
  }

  return (
    <main className="card">
      <h1>Entrar</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Usuário
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        <label>
          Senha
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && <p className="error">{error}</p>}
        <button disabled={loading}>{loading ? "Entrando..." : "Entrar"}</button>
      </form>
      <p>
        Não tem conta? <Link to="/register">Criar conta</Link>
      </p>
    </main>
  );
}
