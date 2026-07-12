"use client";

import { useState, useEffect } from "react";
import { motion } from "motion/react";
import { useAuth } from "@/lib/auth";
import { TrendingUp, Loader2, Sun, Moon } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [dark, setDark] = useState(false);
  const { login } = useAuth();

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    const isDark =
      stored === "dark" ||
      (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      {/* Floating theme toggle, top-right of viewport */}
      <button
        onClick={toggleTheme}
        className="glass fixed top-6 right-6 w-[42px] h-[42px] rounded-[14px] flex items-center justify-center text-foreground hover:brightness-110 transition-all cursor-pointer"
        aria-label="Toggle theme"
      >
        {dark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
      </button>

      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
        className="w-full max-w-[420px]"
      >
        <div className="glass bg-card rounded-[28px] p-9">
          {/* Brand row */}
          <div className="flex items-center gap-[14px] mb-7">
            <div
              className="w-[52px] h-[52px] rounded-2xl flex items-center justify-center shrink-0"
              style={{
                background: "linear-gradient(135deg, #2f5bff, #8b5cf6)",
                boxShadow: "0 12px 30px -10px rgba(47,91,255,0.5)",
              }}
            >
              <TrendingUp className="h-6 w-6 text-white" strokeWidth={2.4} />
            </div>
            <div>
              <h1 className="text-[22px] font-bold tracking-[-0.6px] leading-tight">
                FinPilot
              </h1>
              <p className="text-[12px] text-muted-foreground">
                Agent-first finance for Switzerland
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                Username
              </label>
              <input
                type="text"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full h-12 rounded-xl bg-accent px-4 text-[14px] border-0 outline-none focus:ring-2 focus:ring-primary/40 transition-all placeholder:text-muted-foreground"
                placeholder="Enter username"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-12 rounded-xl bg-accent px-4 text-[14px] border-0 outline-none focus:ring-2 focus:ring-primary/40 transition-all placeholder:text-muted-foreground"
                placeholder="Enter password"
                required
              />
            </div>

            {error && (
              <motion.p
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-[13px] text-loss font-medium"
              >
                {error}
              </motion.p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full h-12 rounded-xl bg-primary text-primary-foreground font-semibold text-[15px] hover:brightness-110 active:scale-[0.98] transition-all duration-200 disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2"
              style={{ boxShadow: "0 12px 28px -10px rgba(59,130,246,0.55)" }}
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? "Signing in…" : "Sign In"}
            </button>
          </form>
        </div>
      </motion.div>
    </div>
  );
}
