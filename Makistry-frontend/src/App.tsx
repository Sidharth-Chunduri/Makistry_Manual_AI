// src/App.tsx
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import ProjectPage from "./pages/Project";
import ShareView from "./pages/ShareView";
import SettingsPage from "@/pages/Settings";
import { useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useProgressStore } from "@/stores/useProgressStore";
import PendingActionRunner from "./components/PendingActionRunner";
import FinishLogin from "@/pages/FinishLogin";
import { CreditGateModal } from "@/components/CreditGateModal";
import AppNotifications from "@/components/AppNotifications";
import { useAuthReturn } from "@/hooks/useAuthReturn";
import { GlobalLoadingCursor } from "@/components/GlobalLoadingCursor";

function ProgressBootstrap() {
  const { user } = useAuth();
  const initialize = useProgressStore((s) => s.initialize);
  useEffect(() => {
    if (!user?.sub) return;
    initialize(user.sub);
  }, [initialize, user?.sub]);
  return null;
}

/** Run the BroadcastChannel/localStorage auth-done listener globally */
function AuthReturnBootstrap() {
  useAuthReturn({ navigate: false });
  return null;
}

function AppNotificationsGate() {
  const { user } = useAuth();
  if (!user?.sub) return null;
  return <AppNotifications />;
}

const App = () => (
  <TooltipProvider>
    <Toaster />
    <Sonner />
    <BrowserRouter>
      {/* ← Must be inside Router so useNavigate works */}
      <AuthReturnBootstrap />

      <ProgressBootstrap />
      <PendingActionRunner />
      <CreditGateModal />
      <AppNotificationsGate />
      {/* <GlobalLoadingCursor delayMs={2000} /> */}

      <Routes>
        <Route path="/" element={<Index />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/project/:pid" element={<ProjectPage />} />
        <Route path="/s/:slug" element={<ShareView />} />
        <Route path="/share/:slug" element={<ShareView />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/finish-login" element={<FinishLogin />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  </TooltipProvider>
);

export default App;
