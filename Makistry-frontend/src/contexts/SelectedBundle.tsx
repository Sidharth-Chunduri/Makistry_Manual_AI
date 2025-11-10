// src/contexts/SelectedBundle.tsx
import React, { createContext, useContext, useState } from "react";

export interface Bundle {
  bundle      : number;
  brain_ver   : number | null;
  cad_file_ver: number | null;
  cad_code_ver: number | null;
}

const Ctx = createContext<{
  selected : Bundle | null;
  setBundle: (b: Bundle) => void;
} | null>(null);

export function SelectedBundleProvider({ children }: { children: React.ReactNode }) {
  const [selected, setSelected] = useState<Bundle | null>(null);
  return <Ctx.Provider value={{ selected, setBundle: setSelected }}>{children}</Ctx.Provider>;
}

export function useSelectedBundle() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("SelectedBundleProvider missing");
  return ctx;
}