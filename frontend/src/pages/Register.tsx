import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { request } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";
import { AuthShell, Button, FormError, Input } from "../ui";

export default function Register() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await request("/auth/register", { method: "POST", body: { username, password } });
      await login(username, password); // registro não faz login
      navigate("/");
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      hero="Sua chave nasce no seu dispositivo."
      text="Ao criar a conta, um par de chaves é gerado localmente. A chave privada nunca é enviada ao servidor."
      hex={["e9bc 68fa a474 2c46", "2c88 27a6 0050 1d39"]}
    >
      <div className="page-head">
        <h1 className="title-auth">Criar conta</h1>
        <p className="subtitle">Escolha um usuário e uma senha forte.</p>
      </div>
      <form onSubmit={handleSubmit}>
        <div className="fields">
          <Input
            label="Usuário"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            placeholder="ex: heitor"
            invalid={!!error}
            required
          />
          <Input
            label="Senha"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            placeholder="Mínimo 8 caracteres"
            invalid={!!error}
            required
          />
          {error && <FormError>{error}</FormError>}
        </div>
        <Button disabled={loading}>{loading ? "Criando..." : "Criar conta"}</Button>
      </form>
      <p className="auth-switch">
        Já tem conta? <Link to="/login">Entrar</Link>
      </p>
    </AuthShell>
  );
}
