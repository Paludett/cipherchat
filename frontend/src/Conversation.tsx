import { FormEvent, useEffect, useRef, useState } from "react";
import type { Msg, OpenChat } from "./Chat";
import type { SocketStatus } from "./socket";
import { Avatar, Button, KeyGrid, KeyIcon } from "./ui";

const STATUS_LABEL: Record<Msg["status"], string> = {
  enviando: "enviando...",
  enviada: "enviada",
  offline: "destinatário offline",
  erro: "erro ao enviar",
  recebida: "",
  invalida: "adulterada ou ilegível",
};

const BAD_STATUS: Msg["status"][] = ["offline", "erro", "invalida"];

type Props = {
  chat: OpenChat;
  messages: Msg[];
  connected: boolean;
  socketStatus: SocketStatus;
  onSend: (text: string) => void;
  onTrustNewKey: () => void;
};

export default function Conversation({ chat, messages, connected, socketStatus, onSend, onTrustNewKey }: Props) {
  const [draft, setDraft] = useState("");
  const [inspected, setInspected] = useState<Msg | null>(null);
  const [showKey, setShowKey] = useState(true);
  const listRef = useRef<HTMLUListElement>(null);
  const name = chat.contact.username;

  // Rola até o fim quando chega mensagem nova
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length]);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    onSend(draft);
    setDraft("");
  }

  return (
    <div className="conversation">
      <section className="conversation-main">
        <header className="conv-header">
          <div className="conv-peer">
            <Avatar name={name} />
            <div>
              <h3 className="conv-name">{name}</h3>
              <span className={`conv-status ${socketStatus === "conectado" ? "is-connected" : ""}`}>
                {socketStatus} · cifrado de ponta a ponta
              </span>
            </div>
          </div>
          <Button variant="secondary" aria-expanded={showKey} onClick={() => setShowKey(!showKey)}>
            <KeyIcon />
            Chave do contato
          </Button>
        </header>

        {showKey && (
          <div className="key-panel">
            <KeyGrid fingerprint={chat.fingerprint} columns={8} />
            <p>
              Confirme esse código com <strong>{name}</strong> por outro canal. Se for igual ao que aparece do outro lado,
              ninguém está no meio da conversa.
            </p>
          </div>
        )}

        {chat.changed && (
          <div className="key-alert" role="alert">
            <p>A chave de {name} mudou desde a última conversa. Confirme o novo código antes de confiar.</p>
            <Button variant="danger" onClick={onTrustNewKey}>
              Confiar na nova chave
            </Button>
          </div>
        )}

        {messages.length === 0 ? (
          <div className="empty">Nenhuma mensagem ainda</div>
        ) : (
          <ul className="messages" ref={listRef}>
            {messages.map((m) => (
              <li
                key={m.id}
                className={`msg ${m.mine ? "mine" : ""} ${BAD_STATUS.includes(m.status) ? "is-bad" : ""} ${
                  inspected?.id === m.id ? "is-inspected" : ""
                }`}
                onClick={() => setInspected(m)}
                title="Ver o que o servidor recebeu"
              >
                <span className="msg-text">{m.text}</span>
                {STATUS_LABEL[m.status] && <small className="msg-meta">{STATUS_LABEL[m.status]}</small>}
              </li>
            ))}
          </ul>
        )}

        <form className="composer" onSubmit={submit}>
          <input className="input" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Mensagem" />
          <Button disabled={chat.changed || !connected}>Enviar</Button>
        </form>
      </section>

      {/* Painel de inspeção, o que o servidor viu ao lado do texto que só os dois leem */}
      {inspected && (
        <aside className="inspect">
          <div className="inspect-head">
            <h3>Inspeção</h3>
            <Button variant="secondary" size="sm" onClick={() => setInspected(null)}>
              Fechar
            </Button>
          </div>
          <section>
            <h4>Texto claro (só no navegador)</h4>
            <p>{inspected.text}</p>
          </section>
          <section>
            <h4>AAD (autenticado, não cifrado)</h4>
            <code>{inspected.aad}</code>
          </section>
          <section>
            <h4>encrypted_key (AES embrulhada com RSA-OAEP)</h4>
            <code>{inspected.envelope.encrypted_key}</code>
          </section>
          <section>
            <h4>iv</h4>
            <code>{inspected.envelope.iv}</code>
          </section>
          <section>
            <h4>ciphertext (AES-GCM)</h4>
            <code>{inspected.envelope.ciphertext}</code>
          </section>
        </aside>
      )}
    </div>
  );
}
