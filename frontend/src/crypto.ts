// Par RSA-OAEP gerado no navegador  
// A privada é criada com extractable: false e 
// fica no IndexedDB como CryptoKey, nunca sai daqui
// Outro navegador = outro IndexedDB = outra chave

const RSA: RsaHashedKeyGenParams = {
  name: "RSA-OAEP",
  modulusLength: 2048,
  publicExponent: new Uint8Array([1, 0, 1]), // 65537
  hash: "SHA-256",
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("e2ee-chat", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("keys");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// Uma operação na store "keys" (chave = id do usuário, valor = CryptoKeyPair)
async function store<T>(mode: IDBTransactionMode, op: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const req = op(db.transaction("keys", mode).objectStore("keys"));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function getOrCreateKeyPair(userId: string): Promise<CryptoKeyPair> {
  const saved = await store<CryptoKeyPair | undefined>("readonly", (s) => s.get(userId));
  if (saved) return saved;

  // extractable: false vale só para a privada, a pública é sempre exportável
  const pair = await crypto.subtle.generateKey(RSA, false, ["encrypt", "decrypt"]);
  await store("readwrite", (s) => s.add(pair, userId)).catch(() => {});
  return (await store<CryptoKeyPair>("readonly", (s) => s.get(userId)))!;
}

export function toBase64(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)));
}

export async function fingerprint(spki: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", spki);
  return Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, "0")).join("");
}
