import { auth } from "@/firebase";
import { signInWithCustomToken, signOut } from "firebase/auth";
import { api } from "@/lib/api";

let inflight: Promise<void> | null = null;

/**
 * Ensure a Firebase Auth session exists for Firestore rules that require auth.
 * NO-OP if already signed in (email-link / Google).
 */
export async function ensureFirebaseSession(appJwt: string) {
  try {
    // If already signed in, check if it's still valid
    if (auth.currentUser) {
      try {
        // Try to get a fresh token to verify auth is still valid
        await auth.currentUser.getIdToken(false);
        return; // Auth is valid, no need to re-authenticate
      } catch (tokenError) {
        console.log("Existing Firebase auth token invalid, re-authenticating...");
        // Token is invalid, proceed with re-authentication
      }
    }

    // Prevent concurrent attempts
    if (inflight) {
      console.log("Firebase auth already in progress, waiting...");
      return inflight;
    }

    console.log("Starting Firebase custom token authentication...");
    
    inflight = (async () => {
      try {
        // Get custom token from your backend
        const { data } = await api.post("/auth/firebase_custom", null, {
          headers: { Authorization: `Bearer ${appJwt}` },
        });
        const customToken: string = data.customToken;
        
        // Sign in with custom token
        await signInWithCustomToken(auth, customToken);
        console.log("Firebase authentication successful");
        
      } catch (error) {
        console.error("Firebase custom token auth failed:", error);
        throw error;
      }
    })();

    await inflight;
    
  } catch (e) {
    console.warn("ensureFirebaseSession failed:", e);
    // Don't throw - let the app continue without Firebase auth if needed
  } finally {
    inflight = null;
  }
}

export async function destroyFirebaseSession() {
  try {
    if (auth.currentUser) {
      console.log("Signing out of Firebase...");
      await signOut(auth);
    }
  } catch (e) {
    console.warn("Error signing out of Firebase:", e);
  }
}