import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { createPortal } from "react-dom";
import logo from "/Makistry.png"; // adjust path or import your component

interface Props {
  open: boolean;
  onClose?: () => void;                 // optional; you may decide to force a choice
  onLogin: () => void;
  onSignup: () => void;
}

export function AuthGateModal({ open, onClose, onLogin, onSignup }: Props) {
  if (!open) return null;

  const modal = (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative z-[2001] w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
        {onClose && (
          <button
            className="absolute right-3 top-3 p-1 text-gray-500 hover:text-gray-700"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        )}
        <div className="flex flex-col items-center text-center">
          <img src={logo} alt="Makistry" className="h-12 mb-4" />
          <h2 className="text-2xl font-semibold text-[#031926]">
            Join the Maker community
          </h2>
          <p className="mt-2 text-sm text-[#031926]/70 max-w-sm">
            Start innovating today with Makistry!
          </p>

          <div className="mt-8 grid grid-cols-2 gap-3 w-full">
            <Button className="w-full" variant="outline" onClick={onLogin}>
              Log in
            </Button>
            <Button className="w-full" onClick={onSignup}>
              Sign up
            </Button>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}