import type { Contact, Msg } from "./Chat";

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
      <h2>Contatos</h2>
      {contacts.length === 0 && <p>Ninguém online.</p>}
      <ul>
        {contacts.map((c) => {
          const unread = messages.filter((m) => m.contactId === c.id && m.unread).length;
          return (
            <li key={c.id}>
              <button className={c.id === selectedId ? "selected" : ""} onClick={() => onSelect(c.id)}>
                <span className={`dot ${onlineIds.includes(c.id) ? "online" : ""}`} />
                {c.username}
                {unread > 0 && <span className="badge">{unread}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
