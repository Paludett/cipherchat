import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api";
import { useAuth } from "../auth";
import { friendlyError } from "../errors";
import { Avatar, Button, Logo } from "../ui";

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
    <div className="admin">
      <header className="topbar">
        <div className="topbar-brand">
          <Logo />
          <span className="topbar-section">Admin</span>
        </div>
        <Link to="/">Voltar ao chat</Link>
      </header>
      <main className="admin-content">
        <div className="page-head">
          <h1 className="title-page">Administração</h1>
          <p className="subtitle">Gerencie papéis, acesso e status de MFA dos usuários.</p>
        </div>
        {error && <p className="banner-error">{error}</p>}
        <div className="table-card" role="table" aria-label="Usuários">
          <div className="table-row table-head section-label" role="row">
            <span role="columnheader">Usuário</span>
            <span role="columnheader">Papel</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">MFA</span>
            <span role="columnheader" style={{ textAlign: "right" }}>
              Ações
            </span>
          </div>
          {users.items.map((u) => (
            <div className="table-row" role="row" key={u.id}>
              <div className="cell-user" role="cell">
                <Avatar name={u.username} size={34} />
                <span>{u.username}</span>
              </div>
              <div role="cell">
                <select
                  className="select"
                  aria-label={`Papel de ${u.username}`}
                  value={u.role}
                  onChange={(e) => update(u, { role: e.target.value })}
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </div>
              <div role="cell">
                <span className={`pill ${u.is_active ? "is-active" : ""}`}>{u.is_active ? "Ativo" : "Desativado"}</span>
              </div>
              <div role="cell">
                <span className={u.mfa_enabled ? "mfa-yes" : "mfa-no"}>{u.mfa_enabled ? "Sim" : "Não"}</span>
              </div>
              <div className="cell-actions" role="cell">
                <Button variant="secondary" onClick={() => update(u, { is_active: !u.is_active })}>
                  {u.is_active ? "Desativar" : "Ativar"}
                </Button>
                <Button variant="danger" onClick={() => remove(u)}>
                  Remover
                </Button>
              </div>
            </div>
          ))}
          <div className="table-footer">
            <span>
              {users.total === 0
                ? "Nenhum usuário"
                : `${offset + 1}–${Math.min(offset + PAGE_SIZE, users.total)} de ${users.total}`}
            </span>
            <div>
              <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => setOffset(offset - PAGE_SIZE)}>
                Anterior
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={offset + PAGE_SIZE >= users.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Próxima
              </Button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
