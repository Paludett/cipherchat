import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { request } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";

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
    <main className="card">
      <h1>Criar conta</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Usuário
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
        </label>
        <label>
          Senha
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required />
        </label>
        {error && <p className="error">{error}</p>}
        <button disabled={loading}>{loading ? "Criando..." : "Criar conta"}</button>
      </form>
      <p>
        Já tem conta? <Link to="/login">Entrar</Link>
      </p>
    </main>
  );
}
