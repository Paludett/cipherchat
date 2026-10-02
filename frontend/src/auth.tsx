import { createContext, useContext, useState, type ReactNode } from "react";
import { request } from "./api";

// Token só em memória, some ao recarregar a página
// Em troca, nenhum XSS consegue ler o token de localStorage/sessionStorage

type LoginResponse = { mfa_required: false; access_token: string } | { mfa_required: true; mfa_token: string };
type TokenResponse = { access_token: string };

type AuthValue = {
  token: string | null;
  login: (username: string, password: string) => Promise<string | null>;
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
  recoverMfa: (mfaToken: string, backupCode: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);

  // Com MFA ligado devolve o token parcial, que só serve para verify/recover
  async function login(username: string, password: string) {
    const res = await request<LoginResponse>("/auth/login", {
      method: "POST",
      body: { username, password },
    });
    if (res.mfa_required) return res.mfa_token;
    setToken(res.access_token);
    return null;
  }

  async function verifyMfa(mfaToken: string, code: string) {
    const res = await request<TokenResponse>("/auth/mfa/verify", { method: "POST", body: { code }, token: mfaToken });
    setToken(res.access_token);
  }

  async function recoverMfa(mfaToken: string, backupCode: string) {
    const res = await request<TokenResponse>("/auth/mfa/recover", {
      method: "POST",
      body: { backup_code: backupCode },
      token: mfaToken,
    });
    setToken(res.access_token);
  }

  async function logout() {
    const current = token;
    setToken(null);
    // Revoga o jti no servidor, se falhar, o token local já foi descartado
    if (current) await request("/auth/logout", { method: "POST", token: current }).catch(() => {});
  }

  return (
    <AuthContext.Provider value={{ token, login, verifyMfa, recoverMfa, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fora do AuthProvider");
  return ctx;
}
