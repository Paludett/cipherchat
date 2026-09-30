import { ApiError } from "./api";

const messages: Record<string, string> = {
  invalid_credentials: "Usuário ou senha inválidos.",
  username_taken: "Esse nome de usuário já está em uso.",
  weak_password: "Senha fraca. Use pelo menos 8 caracteres.",
  validation_error: "Confira os campos. Usuário: 3 a 32 letras, números ou _.",
  account_disabled: "Conta desativada. Fale com um administrador.",
  rate_limited: "Muitas tentativas. Aguarde um pouco e tente de novo.",
  network_error: "Backend inacessível. Tente novamente em instantes.",
  mfa_not_supported: "Esta conta usa MFA, que ainda não é suportado.",
  internal_error: "Erro inesperado. Tente novamente.",
};

export function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    return messages[err.code] ?? (err.message || messages.internal_error);
  }
  return messages.internal_error;
}
