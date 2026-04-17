"use client";

import { usePathname } from "next/navigation";
import { AuthProvider } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";
import { Search, Bell } from "lucide-react";

const PAGE_META: Record<string, { eyebrow: string; subtitle: string }> = {
  "/": { eyebrow: "Dashboard", subtitle: "Overview" },
  "/portfolio": { eyebrow: "Investments", subtitle: "Investments & Holdings" },
  "/transactions": { eyebrow: "Money in & out", subtitle: "Transactions" },
  "/budgets": { eyebrow: "Budgets", subtitle: "Budgets" },
  "/goals": { eyebrow: "Goals & Milestones", subtitle: "Goals & Milestones" },
  "/stats": { eyebrow: "Financial Insights", subtitle: "Statistics" },
  "/categories": { eyebrow: "Categories", subtitle: "Categories" },
  "/settings": { eyebrow: "Settings", subtitle: "Settings" },
};

function TopbarRight() {
  const initial = "M";
  return (
    <div className="flex items-center gap-[10px]">
      {/* Search box */}
      <div className="glass flex items-center gap-2 px-[14px] py-2 rounded-[14px] w-[280px]">
        <Search className="h-4 w-4 text-muted-foreground shrink-0" strokeWidth={1.8} />
        <input
          readOnly
          placeholder="Search or ask agent…"
          className="flex-1 border-none outline-none bg-transparent text-[13px] text-foreground placeholder:text-muted-foreground cursor-default"
        />
        <kbd className="font-mono text-[10px] px-1.5 py-0.5 rounded-[6px] bg-accent text-muted-foreground shrink-0">⌘K</kbd>
      </div>
      {/* Notification bell */}
      <button className="glass w-[42px] h-[42px] rounded-[14px] border-none flex items-center justify-center cursor-pointer text-foreground hover:bg-accent transition-colors">
        <Bell className="h-[18px] w-[18px]" strokeWidth={1.8} />
      </button>
      {/* User avatar */}
      <div
        className="w-[42px] h-[42px] rounded-[14px] flex items-center justify-center text-white font-bold text-[14px] shrink-0"
        style={{ background: "linear-gradient(135deg, #2f5bff, #8b5cf6)" }}
      >
        {initial}
      </div>
    </div>
  );
}

function Topbar({ pathname }: { pathname: string }) {
  const meta = PAGE_META[pathname] ?? { eyebrow: "", subtitle: "" };
  if (!meta.eyebrow) return null;
  return (
    <div className="flex items-center justify-between px-7 pt-[22px]">
      <div>
        <div className="text-[12px] font-semibold text-[var(--accent)] uppercase mb-1" style={{ letterSpacing: '0.4px' }}>
          {meta.eyebrow}
        </div>
        <h1 className="text-[28px] font-bold tracking-[-0.6px]">{meta.subtitle}</h1>
      </div>
      <TopbarRight />
    </div>
  );
}

export function ClientLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";
  const isPublic = pathname.startsWith("/p/");

  if (isLogin) {
    return (
      <AuthProvider>
        <main className="flex min-h-screen items-center justify-center">
          {children}
        </main>
      </AuthProvider>
    );
  }

  if (isPublic) {
    return <main className="min-h-screen">{children}</main>;
  }

  return (
    <AuthProvider>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <Topbar pathname={pathname} />
          <div className="px-7 py-6">{children}</div>
        </main>
      </div>
    </AuthProvider>
  );
}
