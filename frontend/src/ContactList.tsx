import type { Contact, Msg } from "./Chat";
import { Avatar } from "./ui";

type Props = {
  contacts: Contact[];
  onlineIds: string[];
  messages: Msg[];
  selectedId?: string;
  onSelect: (id: string) => void;
};

export default function ContactList({ contacts, onlineIds, messages, selectedId, onSelect }: Props) {
  return (
    <nav className="contacts">
      <h2 className="section-label">Contatos</h2>
      {contacts.length === 0 && <p className="contacts-empty">Ninguém online.</p>}
      <ul>
        {contacts.map((c) => {
          const thread = messages.filter((m) => m.contactId === c.id);
          const unread = thread.filter((m) => m.unread).length;
          const last = thread[thread.length - 1];
          return (
            <li key={c.id}>
              <button className={`contact ${c.id === selectedId ? "selected" : ""}`} onClick={() => onSelect(c.id)}>
                <Avatar name={c.username} online={onlineIds.includes(c.id)} />
                <span className="contact-text">
                  <span className="contact-name">{c.username}</span>
                  <span className="contact-preview">{last ? last.text : "Nenhuma mensagem ainda"}</span>
                </span>
                {unread > 0 && <span className="badge">{unread}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
