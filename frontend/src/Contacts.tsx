import { FormEvent, useEffect, useState } from "react";
import { ApiError, request } from "./api";
import { useAuth } from "./auth";
import { decryptMessage, encryptMessage, Envelope, fingerprint, formatFingerprint, fromBase64, importPublicKey } from "./crypto";
import { friendlyError } from "./errors";

type Contact = { id: string; username: string };
type Chat = { contact: Contact; publicKey: CryptoKey; fingerprint: string; changed: boolean };
type Msg = { id: string; text: string; status: "enviando" | "enviada" | "falhou" | "recebida" | "invalida" };
type Incoming = Envelope & { msg_id: string; from: string; sent_at: string };

const STATUS_LABEL = {
  enviando: "enviando...",
  enviada: "enviada",
  falhou: "não entregue",
  recebida: "recebida",
  invalida: "adulterada ou ilegível",
};

// polling a cada 5s, troca pelo evento presence do /ws quando o backend enviar
const POLL_MS = 5000;

type Props = { myId: string; ws: WebSocket; privateKey: CryptoKey };

export default function Contacts({ myId, ws, privateKey }: Props) {
  const { token, logout } = useAuth();
  const [online, setOnline] = useState<Contact[]>([]);
  const [chat, setChat] = useState<Chat | null>(null);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");

  function handleError(err: unknown) {
    if (err instanceof ApiError && err.code === "unauthenticated") logout();
    else setError(friendlyError(err));
  }

  useEffect(() => {
    const load = () => request<Contact[]>("/users/online", { token }).then(setOnline).catch(handleError);
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, []);

  function setStatus(id: string, status: Msg["status"]) {
    setMessages((msgs) => msgs.map((m) => (m.id === id ? { ...m, status } : m)));
  }

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const data = JSON.parse(e.data);
      if (data.type === "sent") setStatus(data.msg_id, "enviada");
      if (data.type === "error" && data.msg_id) setStatus(data.msg_id, "falhou");
      if (data.type === "message") receive(data);
    }
    ws.addEventListener("message", onMessage);
    return () => ws.removeEventListener("message", onMessage);
  }, [ws, chat]);

  async function receive(data: Incoming) {
    if (chat?.contact.id !== data.from) await openChat(data.from);
    const aad = `${data.msg_id}|${data.from}|${myId}|${data.sent_at}`;
    const text = await decryptMessage(privateKey, data, aad);
    const msg: Msg = text === null
      ? { id: data.msg_id, text: "mensagem inválida", status: "invalida" }
      : { id: data.msg_id, text, status: "recebida" };
    setMessages((msgs) => (msgs.some((m) => m.id === msg.id) ? msgs : [...msgs, msg]));
  }

  // Último fingerprint confiado, para avisar se a chave mudou
  const cacheKey = (contactId: string) => `fingerprint:${myId}:${contactId}`;

  async function openChat(contactId: string) {
    setError("");
    setChat(null);
    setMessages([]);
    try {
      const key = await request<{ public_key: string; username: string }>(`/keys/${contactId}`, { token });
      const contact = { id: contactId, username: key.username };
      const spki = fromBase64(key.public_key);
      const fp = await fingerprint(spki);
      const publicKey = await importPublicKey(spki);
      const trusted = localStorage.getItem(cacheKey(contact.id));
      if (trusted === null) localStorage.setItem(cacheKey(contact.id), fp); 
      setChat({ contact, publicKey, fingerprint: fp, changed: trusted !== null && trusted !== fp });
    } catch (err) {
      if (err instanceof ApiError && err.code === "not_found") setError("Esse contato ainda não publicou uma chave.");
      else handleError(err);
    }
  }

  function trustNewKey() {
    localStorage.setItem(cacheKey(chat!.contact.id), chat!.fingerprint);
    setChat({ ...chat!, changed: false });
  }

  // Só o envelope cifrado sai do navegador, o texto claro fica no state local
  async function send(e: FormEvent) {
    e.preventDefault();
    if (!chat || !draft) return;
    const msg: Msg = { id: crypto.randomUUID(), text: draft, status: "enviando" };
    setMessages((msgs) => [...msgs, msg]);
    setDraft("");

    try {
      const to = chat.contact.id;
      const sent_at = new Date().toISOString();
      const aad = `${msg.id}|${myId}|${to}|${sent_at}`;
      const envelope = await encryptMessage(chat.publicKey, msg.text, aad);
      ws.send(JSON.stringify({ type: "message", msg_id: msg.id, to, sent_at, ...envelope }));
    } catch {
      setStatus(msg.id, "falhou");
    }
  }

  return (
    <section>
      <h2>Online</h2>
      {online.length === 0 && <p>Ninguém online.</p>}
      <ul>
        {online.map((c) => (
          <li key={c.id}>
            <button onClick={() => openChat(c.id)}>{c.username}</button>
          </li>
        ))}
      </ul>

      {error && <p className="error">{error}</p>}

      {chat && (
        <div>
          <h3>Conversa com {chat.contact.username}</h3>
          <p>
            Chave: <code>{formatFingerprint(chat.fingerprint)}</code>
          </p>
          <p>Confirme esse código com {chat.contact.username} por outro canal.</p>
          {chat.changed && (
            <div className="error">
              <p>A chave de {chat.contact.username} mudou desde a última conversa. Confirme o novo código antes de confiar.</p>
              <button onClick={trustNewKey}>Confiar na nova chave</button>
            </div>
          )}

          <ul>
            {messages.map((m) => (
              <li key={m.id}>
                {m.text} <small>({STATUS_LABEL[m.status]})</small>
              </li>
            ))}
          </ul>
          <form onSubmit={send}>
            <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Mensagem" />
            <button disabled={chat.changed}>Enviar</button>
          </form>
        </div>
      )}
    </section>
  );
}
