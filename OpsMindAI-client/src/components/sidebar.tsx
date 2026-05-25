"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
    LayoutDashboard, Shield, Code2, TestTube2, GitBranch,
    Settings, LogOut, Cpu, ChevronLeft, ChevronRight,
} from "lucide-react";
import { useState } from "react";

const navItems = [
    { label: "Dashboard",    href: "/dashboard",          icon: LayoutDashboard, accent: "#06b6d4", hue: 187 },
    { label: "SRE Agent",    href: "/agents/sre",         icon: Shield,          accent: "#06b6d4", hue: 187 },
    { label: "Code Refactor",href: "/agents/code-refactor",icon: Code2,          accent: "#10b981", hue: 160 },
    { label: "Testing Agent",href: "/agents/testing",     icon: TestTube2,       accent: "#8b5cf6", hue: 270 },
    { label: "Pipeline",     href: "/pipeline",           icon: GitBranch,       accent: "#f59e0b", hue: 38  },
];

const bottomItems = [
    { label: "Settings", href: "/settings", icon: Settings },
    { label: "Logout",   href: "/login",    icon: LogOut },
];

function SidebarOrb({ hue, size = 60, delay = 0 }: { hue: number; size?: number; delay?: number }) {
    return (
        <motion.div
            animate={{ scale: [1, 1.15, 1], opacity: [0.3, 0.6, 0.3] }}
            transition={{ duration: 3 + delay, repeat: Infinity, ease: "easeInOut", delay }}
            style={{
                width: size, height: size,
                borderRadius: "50%",
                background: `radial-gradient(circle, hsla(${hue},90%,60%,0.4) 0%, transparent 70%)`,
                filter: `blur(${size * 0.3}px)`,
            }}
        />
    );
}

export function Sidebar() {
    const pathname  = usePathname();
    const [collapsed, setCollapsed] = useState(false);

    return (
        <motion.aside
            initial={{ x: -120, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.7, ease: [0.23, 1, 0.32, 1] }}
            className={`relative flex flex-col h-screen glass-strong border-r transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] z-20 overflow-hidden ${
                collapsed ? "w-[72px]" : "w-[260px]"
            }`}
            style={{ borderRightColor: "rgba(6,182,212,0.1)" }}
        >
            {/* Ambient orbs */}
            <div className="absolute -top-10 -left-10 opacity-40 pointer-events-none">
                <SidebarOrb hue={187} size={100} delay={0} />
            </div>
            <div className="absolute bottom-20 -right-8 opacity-30 pointer-events-none">
                <SidebarOrb hue={270} size={80} delay={1.5} />
            </div>

            {/* Vertical scan line */}
            <motion.div
                animate={{ y: ["0%", "100%"] }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                className="absolute right-0 w-px h-20 z-0 pointer-events-none"
                style={{ background: "linear-gradient(transparent, rgba(6,182,212,0.4), transparent)" }}
            />

            {/* Logo */}
            <div
                className="flex items-center gap-3 px-4 h-16 relative"
                style={{ borderBottom: "1px solid rgba(6,182,212,0.08)" }}
            >
                <div className="relative shrink-0">
                    <motion.div
                        animate={{ rotate: [0, 360] }}
                        transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
                        className="absolute inset-0 w-9 h-9 rounded-lg"
                        style={{
                            background: "conic-gradient(from 0deg, #06b6d4, #8b5cf6, #e879f9, #06b6d4)",
                            filter: "blur(6px)",
                            opacity: 0.6,
                        }}
                    />
                    <div className="relative w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center">
                        <Cpu className="w-5 h-5 text-white" />
                    </div>
                </div>

                <AnimatePresence>
                    {!collapsed && (
                        <motion.div
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -10 }}
                            transition={{ duration: 0.2 }}
                        >
                            <div className="text-base font-bold text-gradient-hero leading-none">OpsMind AI</div>
                            <div className="text-[9px] text-cyan-400/60 font-mono tracking-widest mt-0.5 uppercase">
                                Neural Ops Center
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {/* Collapse toggle */}
            <motion.button
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                onClick={() => setCollapsed(!collapsed)}
                className="absolute -right-3.5 top-20 w-7 h-7 rounded-full flex items-center justify-center z-30"
                style={{
                    background: "rgba(6,12,28,0.9)",
                    border: "1px solid rgba(6,182,212,0.3)",
                    boxShadow: "0 0 12px rgba(6,182,212,0.2)",
                }}
            >
                {collapsed
                    ? <ChevronRight className="w-3 h-3 text-cyan-400" />
                    : <ChevronLeft  className="w-3 h-3 text-cyan-400" />}
            </motion.button>

            {/* Navigation */}
            <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto overflow-x-hidden">
                {!collapsed && (
                    <p className="text-[9px] uppercase tracking-[0.2em] text-cyan-400/30 font-semibold px-3 mb-3 flex items-center gap-2">
                        <span className="flex-1 h-px bg-gradient-to-r from-cyan-400/20 to-transparent" />
                        Navigation
                        <span className="flex-1 h-px bg-gradient-to-l from-cyan-400/20 to-transparent" />
                    </p>
                )}

                {navItems.map((item, i) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link key={item.href} href={item.href}>
                            <motion.div
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: i * 0.06, duration: 0.4 }}
                                whileHover={{ x: collapsed ? 0 : 4, scale: collapsed ? 1.05 : 1 }}
                                whileTap={{ scale: 0.96 }}
                                className={`relative flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-300 group ${
                                    isActive ? "text-white" : "text-slate-400 hover:text-white"
                                }`}
                                style={isActive ? {
                                    background: `linear-gradient(135deg, ${item.accent}15, transparent)`,
                                    boxShadow: `0 0 20px ${item.accent}20, inset 0 0 20px ${item.accent}05`,
                                    border: `1px solid ${item.accent}25`,
                                } : {
                                    border: "1px solid transparent",
                                }}
                            >
                                {/* Active indicator line */}
                                {isActive && (
                                    <motion.div
                                        layoutId="navActive"
                                        className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full"
                                        style={{ background: `linear-gradient(180deg, transparent, ${item.accent}, transparent)` }}
                                        transition={{ type: "spring", stiffness: 400, damping: 35 }}
                                    />
                                )}

                                {/* Icon with glow */}
                                <div
                                    className="relative shrink-0 transition-all duration-300"
                                    style={isActive ? { filter: `drop-shadow(0 0 6px ${item.accent}80)` } : {}}
                                >
                                    <item.icon
                                        className="w-5 h-5 shrink-0 transition-colors"
                                        style={{ color: isActive ? item.accent : undefined }}
                                    />
                                    {isActive && (
                                        <motion.div
                                            animate={{ scale: [1, 1.5, 1], opacity: [0.4, 0, 0.4] }}
                                            transition={{ duration: 2, repeat: Infinity }}
                                            className="absolute inset-0 rounded-full"
                                            style={{ background: item.accent, filter: "blur(6px)" }}
                                        />
                                    )}
                                </div>

                                <AnimatePresence>
                                    {!collapsed && (
                                        <motion.span
                                            initial={{ opacity: 0, width: 0 }}
                                            animate={{ opacity: 1, width: "auto" }}
                                            exit={{ opacity: 0, width: 0 }}
                                            className="text-sm font-medium whitespace-nowrap overflow-hidden"
                                        >
                                            {item.label}
                                        </motion.span>
                                    )}
                                </AnimatePresence>

                                {/* Active pulse dot */}
                                {isActive && !collapsed && (
                                    <motion.div
                                        animate={{ opacity: [0.5, 1, 0.5] }}
                                        transition={{ duration: 1.5, repeat: Infinity }}
                                        className="ml-auto w-1.5 h-1.5 rounded-full"
                                        style={{ background: item.accent }}
                                    />
                                )}

                                {/* Hover corner decorations */}
                                {!isActive && (
                                    <>
                                        <div className="absolute top-1 left-1 w-2 h-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <div className="absolute top-0 left-0 w-full h-px" style={{ background: item.accent }} />
                                            <div className="absolute top-0 left-0 h-full w-px" style={{ background: item.accent }} />
                                        </div>
                                        <div className="absolute bottom-1 right-1 w-2 h-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <div className="absolute bottom-0 right-0 w-full h-px" style={{ background: item.accent }} />
                                            <div className="absolute bottom-0 right-0 h-full w-px" style={{ background: item.accent }} />
                                        </div>
                                    </>
                                )}
                            </motion.div>
                        </Link>
                    );
                })}
            </nav>

            {/* Bottom items */}
            <div className="px-3 py-3 space-y-1" style={{ borderTop: "1px solid rgba(6,182,212,0.08)" }}>
                {bottomItems.map(item => (
                    <Link key={item.href} href={item.href}>
                        <motion.div
                            whileHover={{ x: collapsed ? 0 : 4 }}
                            whileTap={{ scale: 0.97 }}
                            className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-slate-500 hover:text-white transition-all duration-300 group"
                            style={{ border: "1px solid transparent" }}
                            onMouseEnter={e => (e.currentTarget.style.borderColor = "rgba(148,163,184,0.1)")}
                            onMouseLeave={e => (e.currentTarget.style.borderColor = "transparent")}
                        >
                            <item.icon className="w-4 h-4 shrink-0 group-hover:text-slate-300 transition-colors" />
                            <AnimatePresence>
                                {!collapsed && (
                                    <motion.span
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        className="text-sm font-medium whitespace-nowrap"
                                    >
                                        {item.label}
                                    </motion.span>
                                )}
                            </AnimatePresence>
                        </motion.div>
                    </Link>
                ))}
            </div>
        </motion.aside>
    );
}
