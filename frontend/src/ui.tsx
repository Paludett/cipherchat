import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

// Componentes visuais base, sem lógica de app

type InputProps = InputHTMLAttributes<HTMLInputElement> & { label: string; invalid?: boolean };

export function Input({ label, invalid, className = "", ...props }: InputProps) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <input className={`input ${invalid ? "input-invalid" : ""} ${className}`} aria-invalid={invalid || undefined} {...props} />
    </label>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
  size?: "sm" | "md";
};

export function Button({ variant = "primary", size = "md", className = "", ...props }: ButtonProps) {
  return <button className={`btn btn-${variant} btn-${size} ${className}`} {...props} />;
}

export function Avatar({ name, size = 40, online }: { name: string; size?: 34 | 40; online?: boolean }) {
  return (
    <span className={`avatar avatar-${size}`} aria-hidden>
      {name[0]?.toUpperCase()}
      {online !== undefined && <span className={`avatar-dot ${online ? "is-online" : ""}`} />}
    </span>
  );
}

export function Logo({ inverted = false }: { inverted?: boolean }) {
  return (
    <span className={`logo ${inverted ? "logo-inverted" : ""}`}>
      <span className="logo-mark">
        <LockIcon />
      </span>
      <span className="logo-text">E2EE Chat</span>
    </span>
  );
}

// Fingerprint em blocos de 4 hexa, num grid de N colunas
export function KeyGrid({ fingerprint, columns, className = "" }: { fingerprint: string; columns: 4 | 8; className?: string }) {
  const groups = fingerprint.match(/.{1,4}/g) ?? [];
  return (
    <div className={`key-grid key-grid-${columns} ${className}`}>
      {groups.map((g, i) => (
        <span key={i}>{g}</span>
      ))}
    </div>
  );
}

// 6 caixas de dígito por cima de um input real (mantém autofill, pattern e required)
type OtpProps = Omit<InputHTMLAttributes<HTMLInputElement>, "value"> & { value: string };

export function OtpInput({ value, ...props }: OtpProps) {
  const current = Math.min(value.length, 5);
  return (
    <div className="otp">
      <input className="otp-input" value={value} {...props} />
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={`otp-box ${i === current ? "is-current" : ""}`} aria-hidden>
          {value[i] ?? ""}
        </span>
      ))}
    </div>
  );
}

export function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

export function KeyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="8" cy="15" r="4" />
      <path d="M11 12l9-9M17 6l3 3M15 8l2 2" />
    </svg>
  );
}

export function PhoneIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="7" y="2" width="10" height="20" rx="2" />
      <path d="M11 18h2" />
    </svg>
  );
}

// Layout de Login/Registro: painel escuro à esquerda, formulário à direita
export function AuthShell({ hero, text, hex, children }: { hero: string; text: string; hex: [string, string]; children: ReactNode }) {
  return (
    <div className="auth">
      <aside className="auth-hero">
        <Logo inverted />
        <div className="auth-hero-copy">
          <h2 className="title-hero">{hero}</h2>
          <p>{text}</p>
        </div>
        <div className="auth-hero-hex" aria-hidden>
          {hex[0]}
          <br />
          {hex[1]}
        </div>
      </aside>
      <main className="auth-main">
        <div className="auth-form">{children}</div>
      </main>
    </div>
  );
}

// Cartão centralizado das telas de MFA; step = segmentos preenchidos da barra
export function CardPage({ step, wide, children }: { step?: 1 | 2; wide?: boolean; children: ReactNode }) {
  return (
    <div className="card-page">
      <main className={`card ${wide ? "card-wide" : ""}`}>
        {step && (
          <div className="progress" aria-hidden>
            <span className="is-done" />
            <span className={step === 2 ? "is-done" : ""} />
          </div>
        )}
        {children}
      </main>
    </div>
  );
}

export function FormError({ children }: { children: ReactNode }) {
  return (
    <p className="form-error" role="alert">
      {children}
    </p>
  );
}
