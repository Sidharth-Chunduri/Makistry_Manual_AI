// src/lib/firebaseAuth.ts
import { api } from "@/lib/api";
import { auth } from "@/firebase";

export async function exchangeIdToken(idToken: string) {
  const { data } = await api.post("/auth/firebase", { idToken });
  return data.token;          // Makistry JWT
}