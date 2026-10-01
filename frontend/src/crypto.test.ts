import { beforeAll, describe, expect, it } from "vitest";
import { decryptMessage, encryptMessage, Envelope, fromBase64, toBase64 } from "./crypto";

const AAD = "msg-1|alice|bob|2026-10-01T12:00:00Z";
let keys: CryptoKeyPair;

beforeAll(async () => {
  keys = await crypto.subtle.generateKey(
    { name: "RSA-OAEP", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    false,
    ["encrypt", "decrypt"],
  );
});

// Inverte 1 bit do primeiro byte do campo, igual a adulterar o token do Fernet
function tamper(b64: string): string {
  const bytes = new Uint8Array(fromBase64(b64));
  bytes[0] ^= 1;
  return toBase64(bytes.buffer);
}

describe("decryptMessage", () => {
  let envelope: Envelope;

  beforeAll(async () => {
    envelope = await encryptMessage(keys.publicKey, "oi bob", AAD);
  });

  it("decifra o envelope original", async () => {
    expect(await decryptMessage(keys.privateKey, envelope, AAD)).toBe("oi bob");
  });

  it("rejeita ciphertext com 1 byte alterado", async () => {
    const adulterado = { ...envelope, ciphertext: tamper(envelope.ciphertext) };
    expect(await decryptMessage(keys.privateKey, adulterado, AAD)).toBeNull();
  });

  it("rejeita AAD diferente (servidor trocou o remetente)", async () => {
    expect(await decryptMessage(keys.privateKey, envelope, "msg-1|mallory|bob|2026-10-01T12:00:00Z")).toBeNull();
  });
});
