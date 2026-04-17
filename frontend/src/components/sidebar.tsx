"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  TrendingUp,
  ArrowLeftRight,
  BarChart3,
  Tag,
  Settings,
  LogOut,
  Sun,
  Moon,
  PiggyBank,
  Target,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

const nav = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portfolio", icon: TrendingUp },
  { href: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { href: "/stats", label: "Statistics", icon: BarChart3 },
  { href: "/budgets", label: "Budgets", icon: PiggyBank },
  { href: "/goals", label: "Goals", icon: Target },
  { href: "/categories", label: "Categories", icon: Tag },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { logout } = useAuth();
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    const isDark = stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  return (
    <aside className="flex h-screen w-[260px] flex-col glass bg-sidebar shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-3 px-7 h-[80px]">
        <div
          className="h-11 w-11 rounded-2xl flex items-center justify-center shrink-0"
          style={{ background: "linear-gradient(135deg, #2f5bff, #8b5cf6)", boxShadow: "0 6px 20px -6px rgba(47,91,255,0.5)" }}
        >
          <TrendingUp className="h-5 w-5 text-white" strokeWidth={2.5} />
        </div>
        <div>
          <span className="text-[17px] font-semibold tracking-tight">FinPilot</span>
          <p className="text-[11px] text-muted-foreground">Agent-first finance</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-3 space-y-1">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-2xl px-4 py-3 text-[15px] font-medium transition-all duration-200 cursor-pointer active:scale-[0.98] ${
                active
                  ? "bg-primary text-primary-foreground shadow-md shadow-primary/25"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              }`}
            >
              <Icon className="h-[22px] w-[22px] shrink-0" strokeWidth={active ? 2.2 : 1.8} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 space-y-1">
        <button
          onClick={toggleTheme}
          className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-[15px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-all duration-200 cursor-pointer active:scale-[0.98]"
        >
          {dark ? <Sun className="h-[22px] w-[22px]" strokeWidth={1.8} /> : <Moon className="h-[22px] w-[22px]" strokeWidth={1.8} />}
          {dark ? "Light Mode" : "Dark Mode"}
        </button>
        <button
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-[15px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-all duration-200 cursor-pointer active:scale-[0.98]"
        >
          <LogOut className="h-[22px] w-[22px]" strokeWidth={1.8} />
          Logout
        </button>
      </div>
    </aside>
  );
}
