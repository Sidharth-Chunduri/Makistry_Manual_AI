import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { DropdownMenu,
         DropdownMenuTrigger,
         DropdownMenuContent,
         DropdownMenuItem,
         DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { useAuth } from "@/hooks/useAuth";
import { UserDropdown } from "./UserDropdown";


export function LandingTopBar() {
  const nav = useNavigate();
  const { user, logout } = useAuth();
  const goTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const username = user ? user.email.split("@")[0] : "";

  return (
    <header className="sticky top-0 z-40 h-16 w-full bg-white/90 backdrop-blur border-b border-border">
      <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-4 sm:px-6">
        {/* Left cluster */}
        <div className="flex items-center gap-6">
          <button
            onClick={goTop}
            className="flex items-center gap-2 focus:outline-none"
            aria-label="Go to top"
          >
            <img src="/Makistry.png" alt="Makistry" className="h-11 w-auto" />
          </button>

          <nav className="hidden md:flex items-center gap-7 text-sm text-foreground/80">
            <button
              className="hover:text-foreground transition"
              onClick={() => nav("/settings?plan=sub#billing")}
            >
              Pricing
            </button>
            <a
              href="https://makistry.com/info" target="_blank" rel="noopener noreferrer"
              className="hover:text-foreground transition"
            >
              Learn
            </a>
            <button onClick={() => {
              const elk = document.getElementById("projects");
              elk?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}>
              Projects
            </button>
            <button onClick={() => {
              const el = document.getElementById("community");
              el?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}>
              Community
            </button>
          </nav>
        </div>

        {/* Right cluster */}
        {user ? ( <UserDropdown />
        ) : (
          /* Anonymous: original buttons */
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => nav("/login")}>Log in</Button>
            <Button onClick={() => nav("/signup")}>Sign up</Button>
          </div>
        )}
      </div>
    </header>
  );
}