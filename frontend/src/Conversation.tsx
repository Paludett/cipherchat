import { FormEvent, useState } from "react";
import type { Msg, OpenChat } from "./Chat";
import { formatFingerprint } from "./crypto";

const STATUS_LABEL: Record<Msg["status"], string> = {
  enviando: "enviando...",
  enviada: "enviada",
  offline: "destinatário offline",
  erro: "erro ao enviar",
  recebida: "",
  invalida: "adulterada ou ilegível",
};

type Props = {
  chat: OpenChat;
  messages: Msg[];
  connected: boolean;
  onSend: (text: string) => void;
  onTrustNewKey: () => void;
};

export default function Conversation({ chat, messages, connected, onSend, onTrustNewKey }: Props) {
  const [draft, setDraft] = useState("");
  const [inspected, setInspected] = useState<Msg | null>(null);
  const name = chat.contact.username;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    onSend(draft);
    setDraft("");
  }

  return (
    <div className="conversation">
      <section className="messages-pane">
        <h3>{name}</h3>
        <p>
          Chave: <code>{formatFingerprint(chat.fingerprint)}</code>. Confirme esse código com {name} por outro canal.
        </p>
        {chat.changed && (
          <div className="error">
            <p>A chave de {name} mudou desde a última conversa. Confirme o novo código antes de confiar.</p>
            <button onClick={onTrustNewKey}>Confiar na nova chave</button>
          </div>
        )}

        <ul className="messages">
          {messages.map((m) => (
            <li key={m.id} className={`msg ${m.mine ? "mine" : ""}`} onClick={() => setInspected(m)}>
              {m.text}
              <small>{STATUS_LABEL[m.status]}</small>
            </li>
          ))}
        </ul>

        <form className="send" onSubmit={submit}>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Mensagem" />
          <button disabled={chat.changed || !connected}>Enviar</button>
        </form>
      </section>

      {/* Painel de inspeção, o que o servidor viu ao lado do texto que só os dois leem */}
      {inspected && (
        <aside className="inspect">
          <button onClick={() => setInspected(null)}>Fechar</button>
          <h4>Texto claro (só no navegador)</h4>
          <p>{inspected.text}</p>
          <h4>AAD (autenticado, não cifrado)</h4>
          <code>{inspected.aad}</code>
          <h4>encrypted_key (AES embrulhada com RSA-OAEP)</h4>
          <code>{inspected.envelope.encrypted_key}</code>
          <h4>iv</h4>
          <code>{inspected.envelope.iv}</code>
          <h4>ciphertext (AES-GCM)</h4>
          <code>{inspected.envelope.ciphertext}</code>
        </aside>
      )}
    </div>
  );
}
