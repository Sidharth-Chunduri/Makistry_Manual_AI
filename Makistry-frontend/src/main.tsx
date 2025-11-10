// src/main.tsx   (makistry-frontend)

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import "./firebase"; 
import { initTokenManager, installAxios401Retry } from "@/lib/tokenManager";
import { api } from "@/lib/api";

initTokenManager();
installAxios401Retry(api);

import ReactQueryProvider from "./providers/ReactQueryProvider";  // ⬅ path alias @/* already in tsconfig
import { ChatProvider } from "./contexts/ChatStore";
import { AuthProvider } from "@/hooks/useAuth";
import { SelectedBundleProvider } from "./contexts/SelectedBundle";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <ReactQueryProvider>
        <ChatProvider>
          <SelectedBundleProvider>
            <App />
          </SelectedBundleProvider>
        </ChatProvider>
      </ReactQueryProvider>
    </AuthProvider>
  </React.StrictMode>,
);
