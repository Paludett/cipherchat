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
    const req = indexedDB.open("cipherchat", 1);
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

export function fromBase64(b64: string): ArrayBuffer {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
}

export function formatFingerprint(fp: string): string {
  return fp.match(/.{4}/g)!.join(" ");
}

export function importPublicKey(spki: ArrayBuffer): Promise<CryptoKey> {
  return crypto.subtle.importKey("spki", spki, RSA, false, ["encrypt"]);
}

export type Envelope = { encrypted_key: string; iv: string; ciphertext: string };

export async function encryptMessage(publicKey: CryptoKey, text: string, aad: string): Promise<Envelope> {
  const aesKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoder = new TextEncoder();

  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: encoder.encode(aad) },
    aesKey,
    encoder.encode(text),
  );
  const rawKey = await crypto.subtle.exportKey("raw", aesKey);
  const encryptedKey = await crypto.subtle.encrypt({ name: "RSA-OAEP" }, publicKey, rawKey);

  return {
    encrypted_key: toBase64(encryptedKey),
    iv: toBase64(iv.buffer),
    ciphertext: toBase64(ciphertext),
  };
}

export async function decryptMessage(privateKey: CryptoKey, envelope: Envelope, aad: string): Promise<string | null> {
  try {
    const rawKey = await crypto.subtle.decrypt({ name: "RSA-OAEP" }, privateKey, fromBase64(envelope.encrypted_key));
    const aesKey = await crypto.subtle.importKey("raw", rawKey, "AES-GCM", false, ["decrypt"]);
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: fromBase64(envelope.iv), additionalData: new TextEncoder().encode(aad) },
      aesKey,
      fromBase64(envelope.ciphertext),
    );
    return new TextDecoder().decode(plaintext);
  } catch {
    return null;
  }
}
