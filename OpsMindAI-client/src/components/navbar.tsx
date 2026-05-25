"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
    Bell, Search, Sparkles, Shield, Code2, TestTube2, GitBranch,
    User, Settings, LogOut, ChevronDown, X, CheckCircle2, AlertTriangle, Info,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";

interface AgentStatus {
    name: string;
    status: "active" | "idle" | "running" | "error";
    icon: React.ElementType;
}

interface Notification {
    id: string;
    type: "alert" | "success" | "info";
    title: string;
    body: string;
    time: string;
    read: boolean;
}

const AGENT_ICONS: Record<string, React.ElementType> = {
    sre: Shield, refactor: Code2, testing: TestTube2, pipeline: GitBranch,
};

const STATUS_COLORS: Record<string, string> = {
    active:  "#10b981",
    running: "#06b6d4",
    idle:    "#f59e0b",
    error:   "#f43f5e",
};

const SEED_NOTIFICATIONS: Notification[] = [
    { id: "1", type: "alert",   title: "High CPU on staging-api-1",  body: "CPU usage reached 98% — SRE Agent investigating",          time: "2m ago",  read: false },
    { id: "2", type: "alert",   title: "Memory warning on prod-db-1", body: "Memory at 91% — auto-scaling evaluation triggered",       time: "8m ago",  read: false },
    { id: "3", type: "success", title: "Refactor PR opened",          body: "Code Refactor Agent opened PR #47 for auth-service fixes", time: "15m ago", read: false },
    { id: "4", type: "info",    title: "Pipeline completed",          body: "Autonomous pipeline finished — server restarted cleanly",  time: "32m ago", read: true  },
    { id: "5", type: "success", title: "Test suite passed",           body: "1247/1247 tests passing — coverage 96%",                  time: "1h ago",  read: true  },
];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

function getInitials(name: string) {
    return name.split(" ").map(p => p[0]).join("").toUpperCase().slice(0, 2);
}

function NotifIcon({ type }: { type: Notification["type"] }) {
    if (type === "alert")   return <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
    if (type === "success") return <CheckCircle2  className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
    return                         <Info          className="w-3.5 h-3.5 text-cyan-400 shrink-0" />;
}

function HoloDropdown({ children, className = "" }: { children: React.ReactNode; className?: string }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 8, scaleY: 0.95, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, scaleY: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: 6, scaleY: 0.95, filter: "blur(4px)" }}
            transition={{ duration: 0.2, ease: [0.23, 1, 0.32, 1] }}
            className={`absolute right-0 top-full mt-2 z-50 overflow-hidden ${className}`}
            style={{
                background: "rgba(4, 8, 20, 0.92)",
                backdropFilter: "blur(32px) saturate(200%)",
                border: "1px solid rgba(6,182,212,0.15)",
                borderRadius: "16px",
                boxShadow: "0 0 40px rgba(6,182,212,0.08), 0 20px 60px rgba(0,0,0,0.5)",
            }}
        >
            {/* Top holographic edge */}
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent" />
            {children}
        </motion.div>
    );
}

export function Navbar() {
    const [agents, setAgents] = useState<AgentStatus[]>([
        { name: "SRE",      status: "active",  icon: Shield    },
        { name: "Refactor", status: "idle",    icon: Code2     },
        { name: "Testing",  status: "running", icon: TestTube2 },
    ]);

    const fetchAgentStatus = useCallback(async () => {
        try {
            const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
            const res = await fetch(`${API_BASE}/agents/`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
                credentials: "include",
            });
            if (!res.ok) return;
            const data = await res.json();
            if (Array.isArray(data)) {
                setAgents(data.map((a: { name?: string; status?: string }) => ({
                    name:   a.name ?? "Agent",
                    status: (a.status ?? "idle") as AgentStatus["status"],
                    icon:   AGENT_ICONS[String(a.name ?? "").toLowerCase()] ?? Shield,
                })));
            }
        } catch { /* keep defaults */ }
    }, []);

    useEffect(() => {
        fetchAgentStatus();
        const id = setInterval(fetchAgentStatus, 15_000);
        return () => clearInterval(id);
    }, [fetchAgentStatus]);

    const activeCount   = agents.filter(a => a.status === "active" || a.status === "running").length;
    const overallActive = activeCount > 0;

    const [notifications, setNotifications] = useState<Notification[]>(SEED_NOTIFICATIONS);
    const [showNotifs,  setShowNotifs]  = useState(false);
    const [showAgents,  setShowAgents]  = useState(false);
    const [showProfile, setShowProfile] = useState(false);
    const notifsRef  = useRef<HTMLDivElement>(null);
    const agentsRef  = useRef<HTMLDivElement>(null);
    const profileRef = useRef<HTMLDivElement>(null);

    const unreadCount = notifications.filter(n => !n.read).length;
    const markAllRead = () => setNotifications(ns => ns.map(n => ({ ...n, read: true })));
    const dismiss     = (id: string) => setNotifications(ns => ns.filter(n => n.id !== id));
    const markRead    = (id: string) => setNotifications(ns => ns.map(n => n.id === id ? { ...n, read: true } : n));

    const [profile, setProfile] = useState({ name: "Admin User", role: "DevOps Lead", email: "admin@opsmind.ai" });
    useEffect(() => {
        const update = () => {
            try {
                const s = localStorage.getItem("opsmind_profile");
                if (s) setProfile(JSON.parse(s));
            } catch { /* ignore */ }
        };
        update();
        window.addEventListener("opsmind_profile_update", update);
        return () => window.removeEventListener("opsmind_profile_update", update);
    }, []);

    useEffect(() => {
        const handle = (e: MouseEvent) => {
            if (notifsRef.current  && !notifsRef.current.contains(e.target as Node))  setShowNotifs(false);
            if (agentsRef.current  && !agentsRef.current.contains(e.target as Node))  setShowAgents(false);
            if (profileRef.current && !profileRef.current.contains(e.target as Node)) setShowProfile(false);
        };
        document.addEventListener("mousedown", handle);
        return () => document.removeEventListener("mousedown", handle);
    }, []);

    return (
        <motion.header
            initial={{ y: -30, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6, ease: [0.23, 1, 0.32, 1] }}
            className="h-16 flex items-center justify-between px-6 z-10 relative"
            style={{
                background: "rgba(4, 8, 20, 0.7)",
                backdropFilter: "blur(24px) saturate(180%)",
                borderBottom: "1px solid rgba(6,182,212,0.08)",
            }}
        >
            {/* Holographic bottom edge line */}
            <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/20 to-transparent" />

            {/* Search */}
            <div className="relative w-80 group">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 group-focus-within:text-cyan-400 transition-colors z-10" />
                <Input
                    placeholder="Search agents, pipelines, logs..."
                    className="pl-9 h-9 text-sm text-white placeholder:text-slate-600 bg-transparent transition-all duration-300"
                    style={{
                        background: "rgba(6,182,212,0.04)",
                        border: "1px solid rgba(6,182,212,0.1)",
                        borderRadius: "10px",
                    }}
                    onFocus={e => {
                        e.currentTarget.style.borderColor = "rgba(6,182,212,0.4)";
                        e.currentTarget.style.boxShadow   = "0 0 20px rgba(6,182,212,0.1)";
                    }}
                    onBlur={e => {
                        e.currentTarget.style.borderColor = "rgba(6,182,212,0.1)";
                        e.currentTarget.style.boxShadow   = "none";
                    }}
                />
            </div>

            {/* Right controls */}
            <div className="flex items-center gap-2">

                {/* Agents status pill */}
                <div className="relative" ref={agentsRef}>
                    <motion.button
                        onClick={() => setShowAgents(v => !v)}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.97 }}
                        animate={overallActive ? {
                            boxShadow: ["0 0 0 rgba(6,182,212,0)", "0 0 16px rgba(6,182,212,0.3)", "0 0 0 rgba(6,182,212,0)"],
                        } : {}}
                        transition={overallActive ? { duration: 2, repeat: Infinity } : {}}
                        className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full transition-all"
                        style={{
                            background: overallActive ? "rgba(6,182,212,0.08)" : "rgba(245,158,11,0.06)",
                            border: `1px solid ${overallActive ? "rgba(6,182,212,0.25)" : "rgba(245,158,11,0.2)"}`,
                        }}
                    >
                        <motion.div
                            animate={{ opacity: [0.5, 1, 0.5] }}
                            transition={{ duration: 1.5, repeat: Infinity }}
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: overallActive ? "#06b6d4" : "#f59e0b" }}
                        />
                        <Sparkles className="w-3 h-3" style={{ color: overallActive ? "#06b6d4" : "#f59e0b" }} />
                        <span className="text-xs font-medium" style={{ color: overallActive ? "#06b6d4" : "#f59e0b" }}>
                            {activeCount > 0 ? `${activeCount} Active` : "AI Idle"}
                        </span>
                        <ChevronDown className={`w-3 h-3 transition-transform text-slate-500 ${showAgents ? "rotate-180" : ""}`} />
                    </motion.button>

                    <AnimatePresence>
                        {showAgents && (
                            <HoloDropdown className="w-64">
                                <div className="px-4 py-3" style={{ borderBottom: "1px solid rgba(6,182,212,0.08)" }}>
                                    <p className="text-xs font-semibold text-white">Neural Agent Status</p>
                                    <p className="text-[10px] text-slate-500 mt-0.5 font-mono">REAL-TIME · REFRESH 15s</p>
                                </div>
                                <div className="p-2 space-y-1">
                                    {agents.map(agent => (
                                        <div key={agent.name} className="flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/4 transition-colors">
                                            <agent.icon className="w-4 h-4 shrink-0" style={{ color: STATUS_COLORS[agent.status] }} />
                                            <span className="text-sm text-white flex-1">{agent.name}</span>
                                            <div className="flex items-center gap-1.5">
                                                <motion.div
                                                    animate={{ opacity: agent.status === "running" ? [0.4, 1, 0.4] : 1 }}
                                                    transition={{ duration: 1, repeat: Infinity }}
                                                    className="w-1.5 h-1.5 rounded-full"
                                                    style={{ background: STATUS_COLORS[agent.status] }}
                                                />
                                                <span className="text-[10px] capitalize font-mono" style={{ color: STATUS_COLORS[agent.status] }}>
                                                    {agent.status}
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </HoloDropdown>
                        )}
                    </AnimatePresence>
                </div>

                {/* Notifications */}
                <div className="relative" ref={notifsRef}>
                    <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={() => { setShowNotifs(v => !v); if (!showNotifs && unreadCount > 0) markAllRead(); }}
                        className="relative p-2 rounded-xl transition-all"
                        style={{ border: "1px solid transparent" }}
                        onMouseEnter={e => (e.currentTarget.style.borderColor = "rgba(6,182,212,0.15)")}
                        onMouseLeave={e => (e.currentTarget.style.borderColor = "transparent")}
                    >
                        <Bell className="w-4.5 h-4.5 text-slate-400 hover:text-white transition-colors" style={{ width: "18px", height: "18px" }} />
                        <AnimatePresence>
                            {unreadCount > 0 && (
                                <motion.div
                                    initial={{ scale: 0 }}
                                    animate={{ scale: 1 }}
                                    exit={{ scale: 0 }}
                                    className="absolute -top-0.5 -right-0.5"
                                >
                                    <Badge className="w-4 h-4 p-0 flex items-center justify-center text-[9px] border-0 text-white font-bold"
                                        style={{ background: "linear-gradient(135deg, #f43f5e, #e879f9)", boxShadow: "0 0 8px rgba(244,63,94,0.5)" }}>
                                        {unreadCount}
                                    </Badge>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </motion.button>

                    <AnimatePresence>
                        {showNotifs && (
                            <HoloDropdown className="w-80">
                                <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid rgba(6,182,212,0.08)" }}>
                                    <p className="text-sm font-semibold text-white">Notifications</p>
                                    <button onClick={markAllRead} className="text-[11px] text-cyan-400 hover:text-cyan-300 transition-colors font-mono">
                                        MARK ALL READ
                                    </button>
                                </div>
                                <div className="max-h-80 overflow-y-auto">
                                    {notifications.length === 0 ? (
                                        <p className="text-sm text-slate-500 text-center py-8">All clear, Commander.</p>
                                    ) : notifications.map((n, i) => (
                                        <motion.div
                                            key={n.id}
                                            initial={{ opacity: 0, x: 10 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            exit={{ opacity: 0, x: -10 }}
                                            transition={{ delay: i * 0.04 }}
                                            onClick={() => markRead(n.id)}
                                            className="flex items-start gap-3 px-4 py-3 hover:bg-white/3 transition-colors cursor-pointer"
                                            style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}
                                        >
                                            <div className="mt-0.5"><NotifIcon type={n.type} /></div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-start justify-between gap-2">
                                                    <p className={`text-xs font-medium leading-snug ${!n.read ? "text-white" : "text-slate-400"}`}>{n.title}</p>
                                                    <button
                                                        onClick={e => { e.stopPropagation(); dismiss(n.id); }}
                                                        className="text-slate-600 hover:text-slate-300 transition-colors shrink-0"
                                                    >
                                                        <X className="w-3 h-3" />
                                                    </button>
                                                </div>
                                                <p className="text-[10px] text-slate-500 mt-0.5 leading-snug">{n.body}</p>
                                                <p className="text-[10px] text-slate-600 mt-1 font-mono">{n.time}</p>
                                            </div>
                                            {!n.read && (
                                                <motion.div
                                                    animate={{ opacity: [0.5, 1, 0.5] }}
                                                    transition={{ duration: 1.5, repeat: Infinity }}
                                                    className="w-1.5 h-1.5 rounded-full bg-cyan-400 shrink-0 mt-1"
                                                />
                                            )}
                                        </motion.div>
                                    ))}
                                </div>
                            </HoloDropdown>
                        )}
                    </AnimatePresence>
                </div>

                {/* User profile */}
                <div className="relative" ref={profileRef}>
                    <motion.button
                        whileHover={{ scale: 1.01 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => setShowProfile(v => !v)}
                        className="flex items-center gap-3 px-3 py-1.5 rounded-xl transition-all"
                        style={{
                            borderLeft: "1px solid rgba(6,182,212,0.1)",
                            marginLeft: "4px",
                        }}
                    >
                        <div className="hidden sm:block text-right">
                            <p className="text-sm font-medium text-white leading-none">{profile.name}</p>
                            <p className="text-[10px] text-slate-500 mt-0.5 font-mono">{profile.role}</p>
                        </div>
                        <div className="relative">
                            <motion.div
                                animate={{ rotate: [0, 360] }}
                                transition={{ duration: 12, repeat: Infinity, ease: "linear" }}
                                className="absolute -inset-0.5 rounded-full opacity-60"
                                style={{ background: "conic-gradient(from 0deg, #06b6d4, #8b5cf6, #e879f9, #06b6d4)" }}
                            />
                            <Avatar className="relative w-8 h-8">
                                <AvatarFallback className="text-xs font-bold text-white" style={{ background: "rgba(4,8,20,0.9)" }}>
                                    {getInitials(profile.name)}
                                </AvatarFallback>
                            </Avatar>
                        </div>
                        <ChevronDown className={`w-3 h-3 text-slate-500 transition-transform ${showProfile ? "rotate-180" : ""}`} />
                    </motion.button>

                    <AnimatePresence>
                        {showProfile && (
                            <HoloDropdown className="w-56">
                                <div className="px-4 py-4" style={{ borderBottom: "1px solid rgba(6,182,212,0.08)" }}>
                                    <div className="flex items-center gap-3">
                                        <div className="relative">
                                            <motion.div
                                                animate={{ rotate: [0, 360] }}
                                                transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
                                                className="absolute -inset-0.5 rounded-full"
                                                style={{ background: "conic-gradient(from 0deg, #06b6d4, #8b5cf6, #06b6d4)", opacity: 0.7 }}
                                            />
                                            <Avatar className="relative w-9 h-9">
                                                <AvatarFallback className="text-xs font-bold text-white" style={{ background: "rgba(4,8,20,0.9)" }}>
                                                    {getInitials(profile.name)}
                                                </AvatarFallback>
                                            </Avatar>
                                        </div>
                                        <div>
                                            <p className="text-sm font-semibold text-white">{profile.name}</p>
                                            <p className="text-[10px] text-slate-500 font-mono">{profile.email}</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="p-1.5">
                                    {[
                                        { href: "/settings", icon: User,     label: "Edit Profile" },
                                        { href: "/settings", icon: Settings, label: "Settings" },
                                    ].map(item => (
                                        <Link key={item.label} href={item.href} onClick={() => setShowProfile(false)}>
                                            <button className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm text-slate-400 hover:text-white transition-all text-left hover:bg-white/4">
                                                <item.icon className="w-4 h-4" />
                                                {item.label}
                                            </button>
                                        </Link>
                                    ))}
                                    <div className="my-1.5" style={{ borderTop: "1px solid rgba(6,182,212,0.08)" }} />
                                    <Link href="/login" onClick={() => setShowProfile(false)}>
                                        <button className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm text-rose-400 hover:bg-rose-500/8 transition-all text-left">
                                            <LogOut className="w-4 h-4" />
                                            Sign out
                                        </button>
                                    </Link>
                                </div>
                            </HoloDropdown>
                        )}
                    </AnimatePresence>
                </div>
            </div>
        </motion.header>
    );
}
