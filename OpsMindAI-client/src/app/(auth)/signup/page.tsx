"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Eye, EyeOff, Mail, Lock, User, ArrowRight, Cpu, Check, Loader2,
} from "lucide-react";
import { useOAuth } from "@/lib/hooks/use-oauth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const GithubIcon = ({ className }: { className?: string }) => (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
        <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
    </svg>
);

export default function SignupPage() {
    const router = useRouter();
    const { startOAuth } = useOAuth();

    const [showPassword, setShowPassword]   = useState(false);
    const [isLoading, setIsLoading]         = useState(false);
    const [oauthLoading, setOauthLoading]   = useState<"github" | "google" | null>(null);
    const [step, setStep]                   = useState(1);
    const [name, setName]                   = useState("");
    const [email, setEmail]                 = useState("");
    const [password, setPassword]           = useState("");
    const [confirmPassword, setConfirm]     = useState("");
    const [error, setError]                 = useState<string | null>(null);

    async function handleOAuth(provider: "github" | "google") {
        setError(null);
        setOauthLoading(provider);
        try {
            await startOAuth(provider === "github" ? "oauth_github" : "oauth_google");
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            setError(`${provider} sign-up failed: ${msg}`);
            setOauthLoading(null);
        }
    }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (step === 1) { setStep(2); return; }

        if (password !== confirmPassword) { setError("Passwords do not match."); return; }
        setIsLoading(true);
        setError(null);

        try {
            const res = await fetch(`${API_BASE}/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({ email, password, username: name.split(" ")[0].toLowerCase() }),
            });
            const data = await res.json();
            if (!res.ok) { setError(data.detail ?? "Registration failed."); setIsLoading(false); return; }

            if (data.access_token) localStorage.setItem("auth_token", data.access_token);
            const profile = { name, email, role: "DevOps Engineer" };
            localStorage.setItem("opsmind_profile", JSON.stringify(profile));
            window.dispatchEvent(new Event("opsmind_profile_update"));
            router.push("/dashboard");
        } catch {
            setError("Cannot reach the server. Please check your connection.");
            setIsLoading(false);
        }
    }

    return (
        <div className="flex min-h-screen items-center justify-center px-4">
            <motion.div
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease: "easeOut" }}
                className="w-full max-w-md mx-auto"
            >
                <div className="glass-strong rounded-2xl p-8 space-y-6 glow-violet">
                    <div className="space-y-2 text-center">
                        <div className="flex items-center justify-center gap-2 mb-4">
                            <div className="relative">
                                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center">
                                    <Cpu className="w-5 h-5 text-white" />
                                </div>
                                <div className="absolute inset-0 w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500 blur-lg opacity-40" />
                            </div>
                            <span className="text-xl font-bold text-gradient-hero">
                                OpsMind AI
                            </span>
                        </div>
                        <h2 className="text-2xl font-bold text-white">Create account</h2>
                        <p className="text-muted-foreground text-sm">
                            Get started with AI-powered DevOps
                        </p>
                    </div>

                    {/* Step indicator */}
                    <div className="flex items-center gap-2">
                        <div className="flex-1 flex items-center gap-2">
                            <div className="w-8 h-8 rounded-full bg-gradient-to-r from-violet-500 to-cyan-500 flex items-center justify-center text-white text-xs font-bold">
                                {step > 1 ? <Check className="w-4 h-4" /> : "1"}
                            </div>
                            <div className="flex-1 h-0.5 bg-white/10 rounded-full overflow-hidden">
                                <motion.div
                                    className="h-full bg-gradient-to-r from-violet-500 to-cyan-500"
                                    initial={{ width: "0%" }}
                                    animate={{ width: step > 1 ? "100%" : "50%" }}
                                    transition={{ duration: 0.5 }}
                                />
                            </div>
                            <div
                                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 ${step >= 2 ? "bg-gradient-to-r from-violet-500 to-cyan-500 text-white" : "bg-white/10 text-muted-foreground"}`}
                            >
                                2
                            </div>
                        </div>
                    </div>

                    {/* Social Login */}
                    {step === 1 && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                        >
                            {error && (
                                <motion.div
                                    initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                                    className="mb-3 px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm"
                                >
                                    {error}
                                </motion.div>
                            )}
                            <div className="grid grid-cols-2 gap-3">
                                <Button
                                    type="button"
                                    variant="outline"
                                    disabled={oauthLoading !== null}
                                    onClick={() => handleOAuth("github")}
                                    className="bg-white/5 border-white/10 hover:bg-white/10 hover:border-violet-500/30 transition-all duration-300 text-white disabled:opacity-60"
                                >
                                    {oauthLoading === "github"
                                        ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        : <GithubIcon className="w-4 h-4 mr-2" />}
                                    GitHub
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    disabled={oauthLoading !== null}
                                    onClick={() => handleOAuth("google")}
                                    className="bg-white/5 border-white/10 hover:bg-white/10 hover:border-violet-500/30 transition-all duration-300 text-white disabled:opacity-60"
                                >
                                    {oauthLoading === "google"
                                        ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        : <Mail className="w-4 h-4 mr-2" />}
                                    Google
                                </Button>
                            </div>

                            <div className="relative mt-4">
                                <div className="absolute inset-0 flex items-center">
                                    <span className="w-full border-t border-white/10" />
                                </div>
                                <div className="relative flex justify-center text-xs uppercase">
                                    <span className="bg-[#0f172a] px-2 text-muted-foreground">
                                        Or continue with email
                                    </span>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {/* Form */}
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {step === 1 ? (
                            <motion.div
                                key="step1"
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: 20 }}
                                className="space-y-4"
                            >
                                <div className="space-y-2">
                                    <Label htmlFor="name" className="text-white/80 text-sm">
                                        Full Name
                                    </Label>
                                    <div className="relative">
                                        <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                        <Input
                                            id="name"
                                            type="text"
                                            placeholder="John Doe"
                                            value={name}
                                            onChange={e => setName(e.target.value)}
                                            className="pl-10 bg-white/5 border-white/10 focus:border-violet-500/50 focus:ring-violet-500/20 text-white placeholder:text-muted-foreground transition-all duration-300 h-11"
                                            required
                                        />
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label htmlFor="email" className="text-white/80 text-sm">
                                        Email
                                    </Label>
                                    <div className="relative">
                                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                        <Input
                                            id="email"
                                            type="email"
                                            placeholder="you@company.com"
                                            value={email}
                                            onChange={e => setEmail(e.target.value)}
                                            className="pl-10 bg-white/5 border-white/10 focus:border-violet-500/50 focus:ring-violet-500/20 text-white placeholder:text-muted-foreground transition-all duration-300 h-11"
                                            required
                                        />
                                    </div>
                                </div>
                            </motion.div>
                        ) : (
                            <motion.div
                                key="step2"
                                initial={{ opacity: 0, x: 20 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: -20 }}
                                className="space-y-4"
                            >
                                <div className="space-y-2">
                                    <Label htmlFor="password" className="text-white/80 text-sm">
                                        Password
                                    </Label>
                                    <div className="relative">
                                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                        <Input
                                            id="password"
                                            type={showPassword ? "text" : "password"}
                                            placeholder="Create a strong password"
                                            value={password}
                                            onChange={e => setPassword(e.target.value)}
                                            className="pl-10 pr-10 bg-white/5 border-white/10 focus:border-violet-500/50 focus:ring-violet-500/20 text-white placeholder:text-muted-foreground transition-all duration-300 h-11"
                                            required
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowPassword(!showPassword)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-white transition-colors"
                                        >
                                            {showPassword ? (
                                                <EyeOff className="w-4 h-4" />
                                            ) : (
                                                <Eye className="w-4 h-4" />
                                            )}
                                        </button>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <Label
                                        htmlFor="confirmPassword"
                                        className="text-white/80 text-sm"
                                    >
                                        Confirm Password
                                    </Label>
                                    <div className="relative">
                                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                        <Input
                                            id="confirmPassword"
                                            type="password"
                                            placeholder="Confirm your password"
                                            value={confirmPassword}
                                            onChange={e => setConfirm(e.target.value)}
                                            className="pl-10 bg-white/5 border-white/10 focus:border-violet-500/50 focus:ring-violet-500/20 text-white placeholder:text-muted-foreground transition-all duration-300 h-11"
                                            required
                                        />
                                    </div>
                                </div>

                                <div className="flex items-start space-x-2">
                                    <Checkbox
                                        id="terms"
                                        className="border-white/20 data-[state=checked]:bg-violet-500 data-[state=checked]:border-violet-500 mt-0.5"
                                    />
                                    <Label
                                        htmlFor="terms"
                                        className="text-xs text-muted-foreground cursor-pointer leading-relaxed"
                                    >
                                        I agree to the{" "}
                                        <Link
                                            href="#"
                                            className="text-violet-400 hover:text-violet-300"
                                        >
                                            Terms of Service
                                        </Link>{" "}
                                        and{" "}
                                        <Link
                                            href="#"
                                            className="text-violet-400 hover:text-violet-300"
                                        >
                                            Privacy Policy
                                        </Link>
                                    </Label>
                                </div>
                            </motion.div>
                        )}

                        {step === 2 && error && (
                            <motion.div
                                initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                                className="px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm"
                            >
                                {error}
                            </motion.div>
                        )}

                        <div className="flex gap-3">
                            {step > 1 && (
                                <Button
                                    type="button"
                                    variant="outline"
                                    onClick={() => setStep(1)}
                                    className="bg-white/5 border-white/10 hover:bg-white/10 text-white"
                                >
                                    Back
                                </Button>
                            )}
                            <Button
                                type="submit"
                                disabled={isLoading}
                                className="flex-1 h-11 bg-gradient-to-r from-violet-500 to-cyan-500 hover:from-violet-400 hover:to-cyan-400 text-white font-semibold shadow-lg shadow-violet-500/25 transition-all duration-300 hover:shadow-violet-500/40 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-70"
                            >
                                {isLoading ? (
                                    <motion.div
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="flex items-center gap-2"
                                    >
                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                        Creating account...
                                    </motion.div>
                                ) : (
                                    <span className="flex items-center gap-2">
                                        {step === 1 ? "Continue" : "Create account"}
                                        <ArrowRight className="w-4 h-4" />
                                    </span>
                                )}
                            </Button>
                        </div>
                    </form>

                    <p className="text-center text-sm text-muted-foreground">
                        Already have an account?{" "}
                        <Link
                            href="/login"
                            className="text-violet-400 hover:text-violet-300 font-medium transition-colors"
                        >
                            Sign in
                        </Link>
                    </p>
                </div>
            </motion.div>
        </div>
    );
}
