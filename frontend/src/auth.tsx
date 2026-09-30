import { createContext, useContext, useState, type ReactNode } from "react";
import { ApiError, request } from "./api";

// Token só em memória, some ao recarregar a página
// Em troca, nenhum XSS consegue ler o token de localStorage/sessionStorage

type LoginResponse = { mfa_required: false; access_token: string } | { mfa_required: true };

type AuthValue = {
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);

  async function login(username: string, password: string) {
    const res = await request<LoginResponse>("/auth/login", {
      method: "POST",
      body: { username, password },
    });
    if (res.mfa_required) throw new ApiError("mfa_not_supported");
    setToken(res.access_token);
  }

  async function logout() {
    const current = token;
    setToken(null);
    // Revoga o jti no servidor, se falhar, o token local já foi descartado
    if (current) await request("/auth/logout", { method: "POST", token: current }).catch(() => {});
  }

  return <AuthContext.Provider value={{ token, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fora do AuthProvider");
  return ctx;
}
