import { api } from "@/lib/api";

/**
 * Send Firebase email link that returns to /finish-login with ?next=<path>.
 * Example next: "/onboarding" or "/pricing"
 */
export async function sendMagicLink(email: string, nextPath: string = "/") {
  await api.post("/auth/magic_link", { email, next: nextPath });
  localStorage.setItem("emailForSignIn", email);
}