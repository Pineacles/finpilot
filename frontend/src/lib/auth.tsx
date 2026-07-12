"use client";

import { createContext, useContext, useSyncExternalStore, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api } from "./api";

interface AuthCtx {
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthCtx>({
  isAuthenticated: false,
  login: async () => {},
  logout: () => {},
});

// Auth state lives in localStorage, outside React. We read it via
// useSyncExternalStore rather than mirroring it into useState + an effect:
// that would mean calling setState synchronously in an effect body
// (react-hooks/set-state-in-effect) and briefly render the wrong value on
// every mount. useSyncExternalStore instead renders `getServerSnapshot`
// (unauthenticated) during SSR/first paint, then swaps in the real
// `getSnapshot` value as soon as the client can read localStorage, with no
// hydration-mismatch warning, which is exactly what it's designed for.
type AuthListener = () => void;
let authListeners: AuthListener[] = [];

function notifyAuthChange() {
  authListeners.forEach((listener) => listener());
}

function subscribeAuth(callback: AuthListener) {
  authListeners.push(callback);
  window.addEventListener("storage", callback);
  return () => {
    authListeners = authListeners.filter((l) => l !== callback);
    window.removeEventListener("storage", callback);
  };
}

function getAuthSnapshot() {
  return !!localStorage.getItem("token");
}

function getAuthServerSnapshot() {
  return false;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const isAuthenticated = useSyncExternalStore(subscribeAuth, getAuthSnapshot, getAuthServerSnapshot);
  const router = useRouter();

  const login = async (email: string, password: string) => {
    const data = await api.login(email, password);
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("refreshToken", data.refresh_token);
    // Set cookie for middleware auth check
    document.cookie = `token=${data.access_token}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
    notifyAuthChange();
    router.push("/");
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("refreshToken");
    document.cookie = "token=; path=/; max-age=0";
    notifyAuthChange();
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
