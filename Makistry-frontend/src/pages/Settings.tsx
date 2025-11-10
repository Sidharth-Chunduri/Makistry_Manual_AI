// src/pages/Settings.tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { SettingsProfile } from "@/components/SettingsProfile";
import { SettingsBilling } from "@/components/SettingsBilling";
import { useAuth } from "@/hooks/useAuth";

export default function SettingsPage() {
  const nav = useNavigate();
  const { hash } = useLocation();
  const [open, setOpen] = useState(true);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const { user } = useAuth(); 

  const initialTab = useMemo(() => {
    const fromHash =
      hash?.replace("#", "")?.toLowerCase() === "billing" ? "billing" : "profile";
    // If signed out, force Billing as the only accessible tab
    return user ? (fromHash as "profile" | "billing") : "billing";
  }, [hash, user]);

  const [tab, setTab] = useState<"profile" | "billing">(initialTab as any);

  useEffect(() => {
    // Keep tab aligned with initialTab; if user signs out, snap to billing
    setTab(initialTab as any);
    if (!user) window.history.replaceState(null, "", "#billing");
  }, [initialTab, user]);

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) nav(-1);
      }}
    >
      <DialogContent className="sm:max-w-[1100px] lg:max-w-[1200px] h-[90vh] max-h-[90vh] p-0 rounded-2xl overflow-hidden">
        <div className="flex h-full flex-col overflow-hidden">
          <div className="p-6 pb-3 sticky top-0 z-10 bg-card">
            <h2 className="text-2xl font-semibold">Settings</h2>
            <p className="text-sm text-muted-foreground">Manage your account</p>
          </div>

          <Tabs
            value={tab}
            onValueChange={(v) => {
              // 🚫 Block switching to Profile if signed out
              if (!user && v === "profile") {
                setTab("billing");
                window.history.replaceState(null, "", "#billing");
                return;
              }
              setTab(v as any);
              window.history.replaceState(null, "", v === "billing" ? "#billing" : "#profile");
              scrollerRef.current?.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
            }}
            className="flex-1 min-h-0 flex flex-col overflow-hidden"
          >
            <div className="px-6">
              <TabsList>
                <TabsTrigger
                  value="profile"
                  disabled={!user} // ✅ LOCK when signed out
                  title={user ? "Profile" : "Sign in to edit your profile"}
                >
                  Profile
                </TabsTrigger>
                <TabsTrigger value="billing">Plans & Billing</TabsTrigger>
              </TabsList>
            </div>

            <div
              ref={scrollerRef}
              className="relative flex-1 min-h-0 p-6 pt-4 overflow-auto overscroll-contain"
            >
              <TabsContent
                value="profile"
                className="mt-0 transition-opacity duration-200 data-[state=inactive]:opacity-0 data-[state=inactive]:hidden"
              >
                {/* Even if someone forces #profile, the trigger is disabled and onValueChange blocks.
                    Leaving this as-is is fine. */}
                <SettingsProfile />
              </TabsContent>

              <TabsContent
                value="billing"
                className="mt-0 transition-opacity duration-200 data-[state=inactive]:opacity-0 data-[state=inactive]:hidden"
              >
                <SettingsBilling />
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  );
}
