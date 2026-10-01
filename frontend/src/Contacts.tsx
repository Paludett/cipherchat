import { useEffect, useState } from "react";
import { ApiError, request } from "./api";
import { useAuth } from "./auth";
import { fingerprint, formatFingerprint, fromBase64 } from "./crypto";
import { friendlyError } from "./errors";

type Contact = { id: string; username: string };
type Chat = { contact: Contact; fingerprint: string; changed: boolean };

// polling a cada 5s, troca pelo evento presence do /ws quando o backend enviar
const POLL_MS = 5000;

export default function Contacts({ myId }: { myId: string }) {
  const { token, logout } = useAuth();
  const [online, setOnline] = useState<Contact[]>([]);
  const [chat, setChat] = useState<Chat | null>(null);
  const [error, setError] = useState("");

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

  // Último fingerprint confiado, para avisar se a chave mudou
  const cacheKey = (contactId: string) => `fingerprint:${myId}:${contactId}`;

  async function openChat(contact: Contact) {
    setError("");
    setChat(null);
    try {
      const key = await request<{ public_key: string }>(`/keys/${contact.id}`, { token });
      const fp = await fingerprint(fromBase64(key.public_key));
      const trusted = localStorage.getItem(cacheKey(contact.id));
      if (trusted === null) localStorage.setItem(cacheKey(contact.id), fp); 
      setChat({ contact, fingerprint: fp, changed: trusted !== null && trusted !== fp });
    } catch (err) {
      if (err instanceof ApiError && err.code === "not_found") setError(`${contact.username} ainda não publicou uma chave.`);
      else handleError(err);
    }
  }

  function trustNewKey() {
    localStorage.setItem(cacheKey(chat!.contact.id), chat!.fingerprint);
    setChat({ ...chat!, changed: false });
  }

  return (
    <section>
      <h2>Online</h2>
      {online.length === 0 && <p>Ninguém online.</p>}
      <ul>
        {online.map((c) => (
          <li key={c.id}>
            <button onClick={() => openChat(c)}>{c.username}</button>
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
        </div>
      )}
    </section>
  );
}
