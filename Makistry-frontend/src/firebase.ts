// src/firebase.ts
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import {
  initializeFirestore,
  persistentLocalCache,
  persistentMultipleTabManager,
} from "firebase/firestore";

const firebaseConfig = {
  apiKey:     import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId:  import.meta.env.VITE_FIREBASE_PROJECT_ID,
};

console.log("[Firebase] Environment variables loaded:", {
  VITE_FIREBASE_API_KEY: import.meta.env.VITE_FIREBASE_API_KEY ? "✓ Present" : "✗ Missing",
  VITE_FIREBASE_AUTH_DOMAIN: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN ? "✓ Present" : "✗ Missing", 
  VITE_FIREBASE_PROJECT_ID: import.meta.env.VITE_FIREBASE_PROJECT_ID ? "✓ Present" : "✗ Missing",
});

console.log("[Firebase] Config object:", firebaseConfig);

for (const [k, v] of Object.entries(firebaseConfig)) {
  if (!v) console.error(`[Firebase config] Missing ${k}`);
}

export const app  = initializeApp(firebaseConfig);
export const auth = getAuth(app);

// ✅ Force long polling to avoid WebChannel 400 errors
export const db = initializeFirestore(app, {
  ignoreUndefinedProperties: true,
  
  // 🔧 Force long polling to avoid WebChannel transport errors
  experimentalForceLongPolling: true,

  // Stable IndexedDB cache across tabs
  localCache: persistentLocalCache({
    tabManager: persistentMultipleTabManager(),
  }),
});