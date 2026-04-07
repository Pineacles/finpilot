"use client";

import { usePathname } from "next/navigation";
import { AuthProvider } from "@/lib/auth";
import { Sidebar } from "@/components/sidebar";

export function ClientLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLogin = pathname === "/login";

  return (
    <AuthProvider>
      {isLogin ? (
        <main className="flex min-h-screen items-center justify-center">
          {children}
        </main>
      ) : (
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-6xl px-6 py-8 lg:px-10">{children}</div>
          </main>
        </div>
      )}
    </AuthProvider>
  );
}
