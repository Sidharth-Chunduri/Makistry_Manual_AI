// src/components/GoogleButton.tsx
import { Button } from "@/components/ui/button";
import { FcGoogle } from "react-icons/fc";
import { GoogleAuthProvider, signInWithPopup } from "firebase/auth";
import { auth } from "@/firebase";
import { exchangeIdToken } from "@/lib/firebaseAuth";
import { useAuth } from "@/hooks/useAuth";
import { useNavigate } from "react-router-dom";

interface Props {
  className?: string;
  /* optional callback: pendingQuery replay, custom route, etc. */
  onSuccess?: () => void;
}

export function GoogleButton({ className, onSuccess }: Props) {
  const { login } = useAuth();
  const nav = useNavigate();

  const handle = async () => {
    try {
      console.log("Starting Google OAuth flow...");
      const { user } = await signInWithPopup(auth, new GoogleAuthProvider());
      console.log("Google OAuth successful, got user:", user.email);
      
      const idToken = await user.getIdToken();
      console.log("Got ID token, exchanging for JWT...");
      
      const jwt = await exchangeIdToken(idToken);
      console.log("Got JWT token, logging in...");
      
      login(jwt);

      // If parent gave us something to do, run it; else go home.
      if (onSuccess) onSuccess();
      else nav("/");
    } catch (error) {
      console.error("Google OAuth failed:", error);
      alert(`Login failed: ${error.message || error}`);
    }
  };

  return (
    <Button
      onClick={handle}
      variant="outline"
      className={`w-full flex items-center justify-center gap-2 ${className ?? ""}`}
    >
      <FcGoogle className="h-5 w-5" />
      Continue with Google
    </Button>
  );
}
