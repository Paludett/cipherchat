import { useEffect, useState } from "react";
import { ApiError, request } from "./api";
import { useAuth } from "./auth";
import ContactList from "./ContactList";
import Conversation from "./Conversation";
import { decryptMessage, encryptMessage, Envelope, fingerprint, fromBase64, importPublicKey } from "./crypto";
import { friendlyError } from "./errors";
import { useSocket } from "./socket";

export type Contact = { id: string; username: string };
export type OpenChat = { contact: Contact; publicKey: CryptoKey; fingerprint: string; changed: boolean };
export type Msg = {
  id: string;
  contactId: string;
  mine: boolean;
  text: string;
  status: "enviando" | "enviada" | "offline" | "erro" | "recebida" | "invalida";
  unread: boolean;
  envelope: Envelope;
  aad: string;
};
type Incoming = Envelope & { msg_id: string; from: string; sent_at: string };

// polling a cada 5s, troca pelo evento presence do /ws quando o backend enviar
const POLL_MS = 5000;

// Histórico só em memória, some ao recarregar e o servidor nunca guarda mensagens
export default function Chat({ myId, privateKey }: { myId: string; privateKey: CryptoKey }) {
  const { token, logout } = useAuth();
  const [online, setOnline] = useState<Contact[]>([]);
  const [names, setNames] = useState<Record<string, string>>({}); // quem já conversou, mesmo offline
  const [messages, setMessages] = useState<Msg[]>([]);
  const [chat, setChat] = useState<OpenChat | null>(null);
  const [error, setError] = useState("");
  const { socket, status } = useSocket(onSocketMessage);

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

  useEffect(() => {
    if (!socket) setMessages((msgs) => msgs.map((m) => (m.status === "enviando" ? { ...m, status: "erro" } : m)));
  }, [socket]);

  function setStatus(id: string, status: Msg["status"]) {
    setMessages((msgs) => msgs.map((m) => (m.id === id ? { ...m, status } : m)));
  }

  function onSocketMessage(data: any) {
    if (data.type === "sent") setStatus(data.msg_id, "enviada");
    if (data.type === "error" && data.msg_id) setStatus(data.msg_id, data.error.code === "offline" ? "offline" : "erro");
    if (data.type === "message") receive(data).catch(handleError);
  }

  async function receive(data: Incoming) {
    const aad = `${data.msg_id}|${data.from}|${myId}|${data.sent_at}`;
    const text = await decryptMessage(privateKey, data, aad);
    const { encrypted_key, iv, ciphertext } = data;
    const msg: Msg = {
      id: data.msg_id,
      contactId: data.from,
      mine: false,
      text: text ?? "mensagem inválida",
      status: text === null ? "invalida" : "recebida",
      unread: chat?.contact.id !== data.from,
      envelope: { encrypted_key, iv, ciphertext },
      aad,
    };
    setMessages((msgs) => (msgs.some((m) => m.id === msg.id) ? msgs : [...msgs, msg]));
    if (!names[data.from]) await rememberName(data.from);
  }

  async function rememberName(contactId: string) {
    const known = online.find((c) => c.id === contactId);
    const username = known ? known.username : (await fetchKey(contactId)).username;
    setNames((n) => ({ ...n, [contactId]: username }));
  }

  function fetchKey(contactId: string) {
    return request<{ public_key: string; username: string }>(`/keys/${contactId}`, { token });
  }

  const cacheKey = (contactId: string) => `fingerprint:${myId}:${contactId}`;

  async function openChat(contactId: string) {
    setError("");
    setChat(null);
    setMessages((msgs) => msgs.map((m) => (m.contactId === contactId ? { ...m, unread: false } : m)));
    try {
      const key = await fetchKey(contactId);
      const contact = { id: contactId, username: key.username };
      const spki = fromBase64(key.public_key);
      const fp = await fingerprint(spki);
      const publicKey = await importPublicKey(spki);
      const trusted = localStorage.getItem(cacheKey(contact.id));
      if (trusted === null) localStorage.setItem(cacheKey(contact.id), fp);
      setNames((n) => ({ ...n, [contactId]: key.username }));
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
  async function send(text: string) {
    const id = crypto.randomUUID();
    const to = chat!.contact.id;
    const sent_at = new Date().toISOString();
    const aad = `${id}|${myId}|${to}|${sent_at}`;
    const envelope = await encryptMessage(chat!.publicKey, text, aad);
    const msg: Msg = { id, contactId: to, mine: true, text, status: "enviando", unread: false, envelope, aad };
    setMessages((msgs) => [...msgs, msg]);
    socket!.send(JSON.stringify({ type: "message", msg_id: id, to, sent_at, ...envelope }));
  }

  // Lista estilo WhatsApp, quem está online + quem já tem conversa
  const contacts = [...online];
  for (const [id, username] of Object.entries(names)) {
    if (!contacts.some((c) => c.id === id)) contacts.push({ id, username });
  }

  return (
    <div className="chat">
      <ContactList
        contacts={contacts}
        onlineIds={online.map((c) => c.id)}
        messages={messages}
        selectedId={chat?.contact.id}
        onSelect={openChat}
      />
      <div className="chat-main">
        <p className={`socket ${status === "conectado" ? "" : "error"}`}>{status}</p>
        {error && <p className="error">{error}</p>}
        {chat ? (
          <Conversation
            key={chat.contact.id}
            chat={chat}
            messages={messages.filter((m) => m.contactId === chat.contact.id)}
            connected={socket !== null}
            onSend={send}
            onTrustNewKey={trustNewKey}
          />
        ) : (
          <p>Escolha um contato para conversar.</p>
        )}
      </div>
    </div>
  );
}
