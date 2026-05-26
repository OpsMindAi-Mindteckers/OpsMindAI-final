"use client";
 
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Eye, EyeOff, Mail, Lock, ArrowRight,
    Cpu, Shield, Zap, Activity, GitBranch,
} from "lucide-react";
import { useOAuth } from "@/lib/hooks/use-oauth";
 
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
 
// ── Icons ──────────────────────────────────────────────────────────────────────
 
const GithubIcon = ({ className }: { className?: string }) => (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
        <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
    </svg>
);
 
const GoogleIcon = ({ className }: { className?: string }) => (
    <svg viewBox="0 0 24 24" className={className}>
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
);
 
// ── Feature cards (left panel) ─────────────────────────────────────────────────
 
const FEATURES = [
    { icon: Shield,    title: "SRE Agent",           desc: "Auto-detect & resolve server failures",  color: "#06b6d4", hue: 187 },
    { icon: Zap,       title: "Code Refactor Agent", desc: "Intelligent bug detection & fixing",      color: "#10b981", hue: 160 },
    { icon: Activity,  title: "Testing Agent",       desc: "Automated testing & validation",          color: "#8b5cf6", hue: 270 },
    { icon: GitBranch, title: "Pipeline Engine",     desc: "Autonomous CI/CD orchestration",          color: "#e879f9", hue: 300 },
];
 
function HoloFeatureCard({
    icon: Icon, title, desc, color, hue, index,
}: typeof FEATURES[0] & { index: number }) {
    const [hovered, setHovered] = useState(false);
    return (
        <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.5 + index * 0.1, duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            className="relative flex items-center gap-4 p-3 rounded-xl overflow-hidden transition-all duration-500"
            style={{
                background: hovered ? `hsla(${hue},90%,50%,0.06)` : "rgba(4,8,20,0.4)",
                border: `1px solid ${hovered ? color + "40" : "rgba(6,182,212,0.08)"}`,
                boxShadow: hovered ? `0 0 30px ${color}15` : "none",
            }}
        >
            {hovered && (
                <motion.div
                    initial={{ x: "-100%", opacity: 0 }}
                    animate={{ x: "200%", opacity: 1 }}
                    transition={{ duration: 0.6, ease: "easeOut" }}
                    className="absolute inset-0 pointer-events-none"
                    style={{ background: `linear-gradient(105deg, transparent 30%, ${color}10, transparent 70%)` }}
                />
            )}
            <motion.div
                animate={hovered ? { scale: 1.1, rotate: 5 } : { scale: 1, rotate: 0 }}
                transition={{ type: "spring", stiffness: 300, damping: 20 }}
                className="relative w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                style={{ background: `${color}12`, border: `1px solid ${color}25` }}
            >
                <Icon className="w-5 h-5" style={{ color }} />
                {hovered && (
                    <motion.div
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: 2, opacity: 0 }}
                        transition={{ duration: 0.6 }}
                        className="absolute inset-0 rounded-lg"
                        style={{ background: color }}
                    />
                )}
            </motion.div>
            <div>
                <p className="font-semibold text-white text-sm">{title}</p>
                <p className="text-slate-500 text-xs mt-0.5">{desc}</p>
            </div>
        </motion.div>
    );
}
 
// ── Page ───────────────────────────────────────────────────────────────────────
 
export default function LoginPage() {
    const router = useRouter();
    const { startOAuth } = useOAuth();
 
    const [showPassword, setShowPassword] = useState(false);
    const [isLoading,    setIsLoading]    = useState(false);
    const [oauthLoading, setOauthLoading] = useState<"github" | "google" | null>(null);
    const [email,    setEmail]    = useState("");
    const [password, setPassword] = useState("");
    const [error,    setError]    = useState<string | null>(null);
 
    async function handleOAuth(provider: "github" | "google") {
        setError(null);
        setOauthLoading(provider);
        try {
            await startOAuth(provider === "github" ? "oauth_github" : "oauth_google");
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            setError(`${provider} sign-in failed: ${msg}`);
            setOauthLoading(null);
        }
    }
 
    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setIsLoading(true);
        setError(null);
        try {
            const res = await fetch(`${API_BASE}/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ email, password }),
            });
            const data = await res.json();
            if (!res.ok) {
                setError(data.detail ?? "Login failed. Please check your credentials.");
                setIsLoading(false);
                return;
            }
            if (data.access_token) localStorage.setItem("auth_token", data.access_token);
            const profile = {
                name:  data.username || (data.user_email?.split("@")[0] ?? "User"),
                email: data.user_email ?? email,
                role:  "DevOps Engineer",
            };
            localStorage.setItem("opsmind_profile", JSON.stringify(profile));
            window.dispatchEvent(new Event("opsmind_profile_update"));
            router.push("/dashboard");
        } catch {
            try {
                const testRes = await fetch(`${API_BASE}/auth/test-token`, { credentials: "include" });
                if (testRes.ok) {
                    const testData = await testRes.json();
                    localStorage.setItem("auth_token", testData.access_token);
                    const profile = { name: "Dev User", email: email || "dev@local", role: "DevOps Engineer" };
                    localStorage.setItem("opsmind_profile", JSON.stringify(profile));
                    window.dispatchEvent(new Event("opsmind_profile_update"));
                    router.push("/dashboard");
                    return;
                }
            } catch { /* ignore */ }
            setError("Cannot reach the server. Please check your connection.");
            setIsLoading(false);
        }
    }
 
    const anyLoading = isLoading || oauthLoading !== null;
 
    return (
        <div className="flex min-h-screen items-center justify-center px-4 py-12">
            <div className="flex w-full max-w-5xl items-center gap-20">
 
                {/* ── Left — Cinematic branding ──────────────────────────────── */}
                <motion.div
                    initial={{ opacity: 0, x: -60 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.9, ease: [0.23, 1, 0.32, 1] }}
                    className="hidden lg:flex flex-col flex-1 space-y-8"
                >
                    {/* Logo */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="flex items-center gap-4"
                    >
                        <div className="relative">
                            <motion.div
                                animate={{ rotate: [0, 360] }}
                                transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
                                className="absolute -inset-2 rounded-2xl"
                                style={{
                                    background: "conic-gradient(from 0deg, #06b6d4, #8b5cf6, #e879f9, #06b6d4)",
                                    filter: "blur(8px)",
                                    opacity: 0.5,
                                }}
                            />
                            <div
                                className="relative w-14 h-14 rounded-2xl bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center"
                                style={{ boxShadow: "0 0 40px rgba(6,182,212,0.3)" }}
                            >
                                <Cpu className="w-7 h-7 text-white" />
                            </div>
                        </div>
                        <div>
                            <div className="text-3xl font-bold text-gradient-hero">OpsMind AI</div>
                            <div className="text-[11px] font-mono text-cyan-400/50 tracking-widest uppercase mt-1">
                                Neural Operations Platform
                            </div>
                        </div>
                    </motion.div>
 
                    {/* Headline */}
                    <div className="space-y-3">
                        <motion.h1
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.3 }}
                            className="text-4xl font-bold leading-tight text-white"
                        >
                            Intelligent DevOps
                            <br />
                            <span className="text-gradient-cyan">Powered by AI</span>
                        </motion.h1>
                        <motion.p
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.4 }}
                            className="text-slate-400 text-base max-w-md"
                        >
                            Autonomous incident resolution, intelligent code refactoring, and
                            comprehensive testing — all in one platform.
                        </motion.p>
                    </div>
 
                    {/* Feature cards */}
                    <div className="space-y-3">
                        {FEATURES.map((f, i) => (
                            <HoloFeatureCard key={f.title} {...f} index={i} />
                        ))}
                    </div>
                </motion.div>
 
                {/* ── Right — Login form ─────────────────────────────────────── */}
                <motion.div
                    initial={{ opacity: 0, x: 60 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.9, ease: [0.23, 1, 0.32, 1] }}
                    className="w-full max-w-md mx-auto"
                >
                    <div className="glass-strong rounded-2xl p-8 space-y-6 glow-cyan">
 
                        {/* Title */}
                        <div className="space-y-2 text-center">
                            {/* Mobile logo */}
                            <div className="lg:hidden flex items-center justify-center gap-2 mb-4">
                                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-violet-500 flex items-center justify-center">
                                    <Cpu className="w-5 h-5 text-white" />
                                </div>
                                <span className="text-xl font-bold text-gradient-hero">OpsMind AI</span>
                            </div>
                            <h2 className="text-2xl font-bold text-white">Welcome back</h2>
                            <p className="text-slate-400 text-sm">Sign in to your account to continue</p>
                        </div>
 
                        {/* OAuth buttons */}
                        <div className="grid grid-cols-2 gap-3">
                            <Button
                                variant="outline"
                                disabled={anyLoading}
                                onClick={() => handleOAuth("github")}
                                className="bg-white/5 border-white/10 hover:bg-white/10 hover:border-cyan-500/30 transition-all duration-300 text-white"
                            >
                                {oauthLoading === "github" ? (
                                    <div className="w-4 h-4 mr-2 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                ) : (
                                    <GithubIcon className="w-4 h-4 mr-2" />
                                )}
                                GitHub
                            </Button>
                            <Button
                                variant="outline"
                                disabled={anyLoading}
                                onClick={() => handleOAuth("google")}
                                className="bg-white/5 border-white/10 hover:bg-white/10 hover:border-cyan-500/30 transition-all duration-300 text-white"
                            >
                                {oauthLoading === "google" ? (
                                    <div className="w-4 h-4 mr-2 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                ) : (
                                    <GoogleIcon className="w-4 h-4 mr-2" />
                                )}
                                Google
                            </Button>
                        </div>
 
                        {/* Divider */}
                        <div className="relative">
                            <div className="absolute inset-0 flex items-center">
                                <span className="w-full border-t border-white/10" />
                            </div>
                            <div className="relative flex justify-center text-xs uppercase">
                                <span className="bg-[#0f172a] px-2 text-slate-500">Or continue with</span>
                            </div>
                        </div>
 
                        {/* Error banner */}
                        <AnimatePresence>
                            {error && (
                                <motion.div
                                    initial={{ opacity: 0, y: -8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -8 }}
                                    className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400"
                                >
                                    {error}
                                </motion.div>
                            )}
                        </AnimatePresence>
 
                        {/* Login form */}
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="email" className="text-white/80 text-sm">Email</Label>
                                <div className="relative">
                                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                                    <Input
                                        id="email"
                                        type="email"
                                        placeholder="you@company.com"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="pl-10 bg-white/5 border-white/10 focus:border-cyan-500/50 focus:ring-cyan-500/20 text-white placeholder:text-slate-500 transition-all duration-300 h-11"
                                        required
                                        disabled={anyLoading}
                                    />
                                </div>
                            </div>
 
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <Label htmlFor="password" className="text-white/80 text-sm">Password</Label>
                                    <Link href="#" className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
                                        Forgot password?
                                    </Link>
                                </div>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                                    <Input
                                        id="password"
                                        type={showPassword ? "text" : "password"}
                                        placeholder="••••••••"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        className="pl-10 pr-10 bg-white/5 border-white/10 focus:border-cyan-500/50 focus:ring-cyan-500/20 text-white placeholder:text-slate-500 transition-all duration-300 h-11"
                                        required
                                        disabled={anyLoading}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors"
                                    >
                                        {showPassword
                                            ? <EyeOff className="w-4 h-4" />
                                            : <Eye className="w-4 h-4" />
                                        }
                                    </button>
                                </div>
                            </div>
 
                            <div className="flex items-center space-x-2">
                                <Checkbox
                                    id="remember"
                                    className="border-white/20 data-[state=checked]:bg-cyan-500 data-[state=checked]:border-cyan-500"
                                />
                                <Label htmlFor="remember" className="text-sm text-slate-400 cursor-pointer">
                                    Remember me for 30 days
                                </Label>
                            </div>
 
                            <Button
                                type="submit"
                                disabled={anyLoading}
                                className="w-full h-11 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold shadow-lg shadow-cyan-500/25 transition-all duration-300 hover:shadow-cyan-500/40 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-70"
                            >
                                <AnimatePresence mode="wait">
                                    {isLoading ? (
                                        <motion.span
                                            key="loading"
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: 1 }}
                                            exit={{ opacity: 0 }}
                                            className="flex items-center gap-2"
                                        >
                                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                            Signing in...
                                        </motion.span>
                                    ) : (
                                        <motion.span
                                            key="idle"
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: 1 }}
                                            exit={{ opacity: 0 }}
                                            className="flex items-center gap-2"
                                        >
                                            Sign in <ArrowRight className="w-4 h-4" />
                                        </motion.span>
                                    )}
                                </AnimatePresence>
                            </Button>
                        </form>
 
                        <p className="text-center text-sm text-slate-400">
                            Don&apos;t have an account?{" "}
                            <Link href="/signup" className="text-cyan-400 hover:text-cyan-300 font-medium transition-colors">
                                Sign up free
                            </Link>
                        </p>
                    </div>
                </motion.div>
 
            </div>
        </div>
    );
}
 
 