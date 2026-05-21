"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Eye,
    EyeOff,
    Mail,
    Lock,
    ArrowRight,
    Cpu,
    Shield,
    Zap,
} from "lucide-react";

const GithubIcon = ({ className }: { className?: string }) => (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className}>
        <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
    </svg>
);


export default function LoginPage() {
    const [showPassword, setShowPassword] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setTimeout(() => {
            window.location.href = "/dashboard";
        }, 1500);
    };

    return (
        <div className="flex min-h-screen items-center justify-center px-4">
            <div className="flex w-full max-w-5xl items-center gap-16">
                {/* Left side - Branding */}
                <motion.div
                    initial={{ opacity: 0, x: -50 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    className="hidden lg:flex flex-col flex-1 space-y-8"
                >
                    <div className="space-y-4">
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.2 }}
                            className="flex items-center gap-3"
                        >
                            <div className="relative">
                                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500 to-violet-500 flex items-center justify-center">
                                    <Cpu className="w-6 h-6 text-white" />
                                </div>
                                <div className="absolute inset-0 w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500 to-violet-500 blur-lg opacity-50" />
                            </div>
                            <span className="text-2xl font-bold text-gradient-hero">
                                OpsMind AI
                            </span>
                        </motion.div>

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
                            className="text-muted-foreground text-lg max-w-md"
                        >
                            Autonomous incident resolution, intelligent code refactoring, and
                            comprehensive testing — all in one platform.
                        </motion.p>
                    </div>

                    {/* Feature highlights */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.5 }}
                        className="space-y-4"
                    >
                        {[
                            {
                                icon: Shield,
                                title: "SRE Agent",
                                desc: "Auto-detect & resolve server failures",
                                color: "text-cyan-400",
                            },
                            {
                                icon: Zap,
                                title: "Code Refactor Agent",
                                desc: "Intelligent bug detection & fixing",
                                color: "text-emerald-400",
                            },
                            {
                                icon: Cpu,
                                title: "Testing Agent",
                                desc: "Automated testing & validation",
                                color: "text-violet-400",
                            },
                        ].map((feature, i) => (
                            <motion.div
                                key={feature.title}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 0.6 + i * 0.1 }}
                                className="flex items-center gap-4 p-3 rounded-xl glass group hover:glow-cyan transition-all duration-500"
                            >
                                <div
                                    className={`w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center ${feature.color} group-hover:scale-110 transition-transform`}
                                >
                                    <feature.icon className="w-5 h-5" />
                                </div>
                                <div>
                                    <p className="font-semibold text-white text-sm">
                                        {feature.title}
                                    </p>
                                    <p className="text-muted-foreground text-xs">
                                        {feature.desc}
                                    </p>
                                </div>
                            </motion.div>
                        ))}
                    </motion.div>
                </motion.div>

                {/* Right side - Login Form */}
                <motion.div
                    initial={{ opacity: 0, x: 50 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    className="w-full max-w-md mx-auto"
                >
                    <div className="glass-strong rounded-2xl p-8 space-y-6 glow-cyan">
                        <div className="space-y-2 text-center">
                            {/* Mobile logo */}
                            <div className="lg:hidden flex items-center justify-center gap-2 mb-4">
                                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-violet-500 flex items-center justify-center">
                                    <Cpu className="w-5 h-5 text-white" />
                                </div>
                                <span className="text-xl font-bold text-gradient-hero">
                                    OpsMind AI
                                </span>
                            </div>
                            <h2 className="text-2xl font-bold text-white">Welcome back</h2>
                            <p className="text-muted-foreground text-sm">
                                Sign in to your account to continue
                            </p>
                        </div>

                        {/* Social Login */}
                        <div className="grid grid-cols-2 gap-3">
                            <Button
                                variant="outline"
                                className="bg-white/5 border-white/10 hover:bg-white/10 hover:border-cyan-500/30 transition-all duration-300 text-white"
                            >
                                <GithubIcon className="w-4 h-4 mr-2" />
                                GitHub
                            </Button>
                            <Button
                                variant="outline"
                                className="bg-white/5 border-white/10 hover:bg-white/10 hover:border-cyan-500/30 transition-all duration-300 text-white"
                            >
                                <Mail className="w-4 h-4 mr-2" />
                                Google
                            </Button>
                        </div>

                        <div className="relative">
                            <div className="absolute inset-0 flex items-center">
                                <span className="w-full border-t border-white/10" />
                            </div>
                            <div className="relative flex justify-center text-xs uppercase">
                                <span className="bg-[#0f172a] px-2 text-muted-foreground">
                                    Or continue with
                                </span>
                            </div>
                        </div>

                        {/* Login Form */}
                        <form onSubmit={handleSubmit} className="space-y-4">
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
                                        className="pl-10 bg-white/5 border-white/10 focus:border-cyan-500/50 focus:ring-cyan-500/20 text-white placeholder:text-muted-foreground transition-all duration-300 h-11"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <Label htmlFor="password" className="text-white/80 text-sm">
                                        Password
                                    </Label>
                                    <Link
                                        href="#"
                                        className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
                                    >
                                        Forgot password?
                                    </Link>
                                </div>
                                <div className="relative">
                                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                    <Input
                                        id="password"
                                        type={showPassword ? "text" : "password"}
                                        placeholder="••••••••"
                                        className="pl-10 pr-10 bg-white/5 border-white/10 focus:border-cyan-500/50 focus:ring-cyan-500/20 text-white placeholder:text-muted-foreground transition-all duration-300 h-11"
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

                            <div className="flex items-center space-x-2">
                                <Checkbox
                                    id="remember"
                                    className="border-white/20 data-[state=checked]:bg-cyan-500 data-[state=checked]:border-cyan-500"
                                />
                                <Label
                                    htmlFor="remember"
                                    className="text-sm text-muted-foreground cursor-pointer"
                                >
                                    Remember me for 30 days
                                </Label>
                            </div>

                            <Button
                                type="submit"
                                disabled={isLoading}
                                className="w-full h-11 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold shadow-lg shadow-cyan-500/25 transition-all duration-300 hover:shadow-cyan-500/40 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-70"
                            >
                                {isLoading ? (
                                    <motion.div
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="flex items-center gap-2"
                                    >
                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                        Signing in...
                                    </motion.div>
                                ) : (
                                    <span className="flex items-center gap-2">
                                        Sign in
                                        <ArrowRight className="w-4 h-4" />
                                    </span>
                                )}
                            </Button>
                        </form>

                        <p className="text-center text-sm text-muted-foreground">
                            Don&apos;t have an account?{" "}
                            <Link
                                href="/signup"
                                className="text-cyan-400 hover:text-cyan-300 font-medium transition-colors"
                            >
                                Sign up free
                            </Link>
                        </p>
                    </div>
                </motion.div>
            </div>
        </div>
    );
}
