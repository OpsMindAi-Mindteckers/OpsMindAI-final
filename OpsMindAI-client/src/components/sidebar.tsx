"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
    LayoutDashboard,
    Shield,
    Code2,
    TestTube2,
    GitBranch,
    Settings,
    LogOut,
    Cpu,
    ChevronLeft,
    ChevronRight,
} from "lucide-react";
import { useState } from "react";

const navItems = [
    {
        label: "Dashboard",
        href: "/dashboard",
        icon: LayoutDashboard,
        color: "text-cyan-400",
        hoverGlow: "hover:shadow-[0_0_20px_rgba(6,182,212,0.2)]",
    },
    {
        label: "SRE Agent",
        href: "/agents/sre",
        icon: Shield,
        color: "text-cyan-400",
        hoverGlow: "hover:shadow-[0_0_20px_rgba(6,182,212,0.2)]",
    },
    {
        label: "Code Refactor",
        href: "/agents/code-refactor",
        icon: Code2,
        color: "text-emerald-400",
        hoverGlow: "hover:shadow-[0_0_20px_rgba(16,185,129,0.2)]",
    },
    {
        label: "Testing Agent",
        href: "/agents/testing",
        icon: TestTube2,
        color: "text-violet-400",
        hoverGlow: "hover:shadow-[0_0_20px_rgba(139,92,246,0.2)]",
    },
    {
        label: "Pipeline",
        href: "/pipeline",
        icon: GitBranch,
        color: "text-amber-400",
        hoverGlow: "hover:shadow-[0_0_20px_rgba(245,158,11,0.2)]",
    },
];

const bottomItems = [
    { label: "Settings", href: "/settings", icon: Settings },
    { label: "Logout", href: "/login", icon: LogOut },
];

export function Sidebar() {
    const pathname = usePathname();
    const [collapsed, setCollapsed] = useState(false);

    return (
        <motion.aside
            initial={{ x: -100, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className={`relative flex flex-col h-screen glass-strong border-r border-white/5 transition-all duration-300 z-20 ${collapsed ? "w-[72px]" : "w-[260px]"}`}
        >
            {/* Logo */}
            <div className="flex items-center gap-3 px-4 h-16 border-b border-white/5">
                <div className="relative shrink-0">
                    <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 to-violet-500 flex items-center justify-center">
                        <Cpu className="w-5 h-5 text-white" />
                    </div>
                    <div className="absolute inset-0 w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 to-violet-500 blur-md opacity-40" />
                </div>
                {!collapsed && (
                    <motion.span
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="text-lg font-bold text-gradient-hero whitespace-nowrap"
                    >
                        OpsMind AI
                    </motion.span>
                )}
            </div>

            {/* Collapse Toggle */}
            <button
                onClick={() => setCollapsed(!collapsed)}
                className="absolute -right-3 top-20 w-6 h-6 rounded-full bg-[#1e293b] border border-white/10 flex items-center justify-center text-muted-foreground hover:text-white hover:border-cyan-500/30 transition-all z-30"
            >
                {collapsed ? (
                    <ChevronRight className="w-3 h-3" />
                ) : (
                    <ChevronLeft className="w-3 h-3" />
                )}
            </button>

            {/* Navigation */}
            <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
                {!collapsed && (
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground/50 font-semibold px-3 mb-2">
                        Main Menu
                    </p>
                )}
                {navItems.map((item) => {
                    const isActive = pathname === item.href;
                    return (
                        <Link key={item.href} href={item.href}>
                            <motion.div
                                whileHover={{ x: 4 }}
                                whileTap={{ scale: 0.98 }}
                                className={`relative flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-300 group ${item.hoverGlow} ${isActive
                                        ? "bg-white/10 text-white"
                                        : "text-muted-foreground hover:text-white hover:bg-white/5"
                                    }`}
                            >
                                {isActive && (
                                    <motion.div
                                        layoutId="activeTab"
                                        className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 rounded-full bg-gradient-to-b from-cyan-400 to-violet-400"
                                        transition={{ type: "spring", stiffness: 300, damping: 30 }}
                                    />
                                )}
                                <item.icon
                                    className={`w-5 h-5 shrink-0 transition-colors ${isActive ? item.color : "group-hover:" + item.color.replace("text-", "text-")}`}
                                />
                                {!collapsed && (
                                    <span className="text-sm font-medium whitespace-nowrap">
                                        {item.label}
                                    </span>
                                )}
                                {isActive && !collapsed && (
                                    <div className="ml-auto w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                                )}
                            </motion.div>
                        </Link>
                    );
                })}
            </nav>

            {/* Bottom items */}
            <div className="px-3 py-4 border-t border-white/5 space-y-1">
                {bottomItems.map((item) => (
                    <Link key={item.href} href={item.href}>
                        <motion.div
                            whileHover={{ x: 4 }}
                            whileTap={{ scale: 0.98 }}
                            className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-muted-foreground hover:text-white hover:bg-white/5 transition-all duration-300"
                        >
                            <item.icon className="w-5 h-5 shrink-0" />
                            {!collapsed && (
                                <span className="text-sm font-medium">{item.label}</span>
                            )}
                        </motion.div>
                    </Link>
                ))}
            </div>
        </motion.aside>
    );
}
