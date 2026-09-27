import { useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export default function App() {
  const [health, setHealth] = useState("...");

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then((d) => setHealth(`api: ${d.api} / db: ${d.db}`))
      .catch(() => setHealth("backend inacessivel"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui", padding: 32 }}>
      <h1>E2EE Chat</h1>
      <p>{health}</p>
    </main>
  );
}
