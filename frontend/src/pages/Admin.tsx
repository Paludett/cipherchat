import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";

type AdminUser = { id: string; username: string; role: string; is_active: boolean; mfa_enabled: boolean };
type UserList = { items: AdminUser[]; total: number };

const PAGE_SIZE = 10;

export default function Admin() {
  const { token } = useAuth();
  const [users, setUsers] = useState<UserList>({ items: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");

  async function load() {
    try {
      setUsers(await request<UserList>(`/admin/users?limit=${PAGE_SIZE}&offset=${offset}`, { token }));
    } catch (err) {
      setError(friendlyError(err));
    }
  }

  useEffect(() => {
    load();
  }, [offset]);

  // Executa a ação, mostra o erro (se houver) e recarrega a lista
  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
    } catch (err) {
      setError(friendlyError(err));
    }
    await load();
  }

  const update = (u: AdminUser, changes: Partial<Pick<AdminUser, "is_active" | "role">>) =>
    run(() => request(`/admin/users/${u.id}`, { method: "PATCH", body: changes, token }));

  const remove = (u: AdminUser) => {
    if (!window.confirm(`Remover ${u.username} de vez? Não dá para desfazer.`)) return;
    run(() => request(`/admin/users/${u.id}`, { method: "DELETE", token }));
  };

  return (
    <main className="app">
      <header>
        <h1>Administração</h1>
        <Link to="/">Voltar</Link>
      </header>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Usuário</th>
            <th>Papel</th>
            <th>Status</th>
            <th>MFA</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.items.map((u) => (
            <tr key={u.id}>
              <td>{u.username}</td>
              <td>
                <select value={u.role} onChange={(e) => update(u, { role: e.target.value })}>
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </td>
              <td>
                <button onClick={() => update(u, { is_active: !u.is_active })}>
                  {u.is_active ? "Desativar" : "Ativar"}
                </button>
              </td>
              <td>{u.mfa_enabled ? "Sim" : "Não"}</td>
              <td>
                <button onClick={() => remove(u)}>Remover</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <nav>
        <button disabled={offset === 0} onClick={() => setOffset(offset - PAGE_SIZE)}>
          Anterior
        </button>
        <span>
          {offset + 1}-{Math.min(offset + PAGE_SIZE, users.total)} de {users.total}
        </span>
        <button disabled={offset + PAGE_SIZE >= users.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Próxima
        </button>
      </nav>
    </main>
  );
}
