import { useEffect, useState } from "react";
import { ApiError, request } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";

type Me = { id: string; username: string; role: string };

export default function Home() {
  const { token, logout } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    request<Me>("/users/me", { token })
      .then(setMe)
      .catch((err) => {
        // Token expirado (15 min, sem refresh), volta ao login
        if (err instanceof ApiError && err.code === "unauthenticated") logout();
        else setError(friendlyError(err));
      });
  }, []);

  return (
    <main className="card">
      <h1>E2EE Chat</h1>
      {error && <p className="error">{error}</p>}
      {me && <p>Olá, {me.username}!</p>}
      <button onClick={logout}>Sair</button>
    </main>
  );
}
