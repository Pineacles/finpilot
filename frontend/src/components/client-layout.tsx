"use client";

import { usePathname } from "next/navigation";
import { AuthProvider } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";

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

function Topbar({ pathname }: { pathname: string }) {
  const meta = PAGE_META[pathname] ?? { eyebrow: "", subtitle: "" };
  if (!meta.eyebrow) return null;
  return (
    <div className="px-7 pt-[22px]">
      <div className="text-[12px] font-semibold text-primary uppercase mb-1" style={{ letterSpacing: '0.4px' }}>
        {meta.eyebrow}
      </div>
      <h1 className="text-[28px] font-bold tracking-[-0.6px]">{meta.subtitle}</h1>
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
