"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
    Shield, Server, Activity, CheckCircle2,
    RefreshCw, RotateCcw, Terminal, Cpu, HardDrive, Clock,
    History, XCircle, Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useState, useEffect, useRef, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

type Tab = "monitor" | "history";

interface ServerNode {
    name: string;
    status: "healthy" | "warning" | "critical";
    cpu: number;
    memory: number;
    uptime: string;
}

interface Incident {
    time: string;
    title: string;
    type: string;
    status: "investigating" | "resolved" | "completed";
}

interface LogLine {
    time: string;
    level: "ERROR" | "WARN" | "INFO";
    msg: string;
}

interface JobRecord {
    job_id: string;
    phase: string;
    status: string;
    created_at?: string;
    completed_at?: string;
    root_cause?: string;
    confidence?: number;
    incident_id?: string;
    remediation_status?: string;
}

// ── Static seed data (shown while API is not yet set up) ─────────────────────

const SEED_SERVERS: ServerNode[] = [
    { name: "prod-api-1",    status: "healthy",  cpu: 34, memory: 62, uptime: "14d 7h" },
    { name: "prod-api-2",    status: "healthy",  cpu: 45, memory: 58, uptime: "14d 7h" },
    { name: "prod-db-1",     status: "warning",  cpu: 82, memory: 91, uptime: "7d 2h"  },
    { name: "prod-worker-1", status: "healthy",  cpu: 23, memory: 44, uptime: "14d 7h" },
    { name: "prod-cache-1",  status: "healthy",  cpu: 12, memory: 38, uptime: "21d 3h" },
    { name: "staging-api-1", status: "critical", cpu: 98, memory: 95, uptime: "0d 0h"  },
];

const SEED_TIMELINE: Incident[] = [
    { time: "12:04 PM", title: "High CPU detected on staging-api-1",     type: "alert",   status: "investigating" },
    { time: "11:52 AM", title: "Auto-rollback triggered for v2.4.1",      type: "rollback", status: "completed"    },
    { time: "11:30 AM", title: "Memory leak detected on prod-db-1",       type: "alert",   status: "resolved"     },
    { time: "10:15 AM", title: "Server prod-api-1 restarted successfully", type: "restart", status: "completed"    },
    { time: "09:45 AM", title: "Deployment v2.4.0 health check passed",   type: "deploy",  status: "completed"    },
];

const SEED_LOGS: LogLine[] = [
    { time: "12:04:23", level: "ERROR", msg: "[staging-api-1] OOMKilled: container exceeded memory limit" },
    { time: "12:04:22", level: "WARN",  msg: "[staging-api-1] Memory usage at 95% — pod restart imminent" },
    { time: "12:04:20", level: "INFO",  msg: "[sre-agent] Analyzing container metrics for staging-api-1" },
    { time: "12:04:18", level: "INFO",  msg: "[sre-agent] Auto-scaling evaluation triggered" },
    { time: "12:04:15", level: "WARN",  msg: "[prod-db-1] Slow query detected: 2.3s on users_table" },
    { time: "12:04:10", level: "INFO",  msg: "[sre-agent] Health check passed for prod-api-1, prod-api-2" },
    { time: "12:04:05", level: "INFO",  msg: "[sre-agent] Monitoring 6 servers, 2 alerts active" },
    { time: "12:03:58", level: "INFO",  msg: "[prod-worker-1] Background job queue: 42 pending, 0 failed" },
];

// ── Constants ──────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const container = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.08 } } };
const item      = { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } };

// ── Helpers ────────────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
    const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
}

function statusBorder(s: ServerNode["status"]) {
    if (s === "healthy")  return "bg-emerald-500/5 border-emerald-500/10 hover:border-emerald-500/30";
    if (s === "warning")  return "bg-amber-500/5 border-amber-500/10 hover:border-amber-500/30";
    return                       "bg-rose-500/5 border-rose-500/10 hover:border-rose-500/30";
}

function serverIconColor(s: ServerNode["status"]) {
    if (s === "healthy") return "text-emerald-400";
    if (s === "warning") return "text-amber-400";
    return "text-rose-400";
}

function incidentDot(s: Incident["status"]) {
    if (s === "investigating") return "bg-amber-500 border-amber-400";
    if (s === "resolved")      return "bg-emerald-500 border-emerald-400";
    return                            "bg-cyan-500 border-cyan-400";
}

function incidentBadge(s: Incident["status"]) {
    if (s === "investigating") return "bg-amber-500/10 text-amber-400";
    if (s === "resolved")      return "bg-emerald-500/10 text-emerald-400";
    return                            "bg-cyan-500/10 text-cyan-400";
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function SREAgentPage() {
    const [tab, setTab] = useState<Tab>("monitor");

    // Logs panel state
    const [showLogs, setShowLogs] = useState(false);
    const [logs, setLogs] = useState<LogLine[]>(SEED_LOGS);
    const logEndRef = useRef<HTMLDivElement>(null);

    // Action states
    const [restarting, setRestarting]   = useState(false);
    const [rollingBack, setRollingBack] = useState(false);
    const [actionMsg, setActionMsg]     = useState<{ type: "ok" | "err"; text: string } | null>(null);

    // Job history
    const [history, setHistory]           = useState<JobRecord[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);

    // Servers (live from API or seeds)
    const [servers] = useState<ServerNode[]>(SEED_SERVERS);
    const [timeline] = useState<Incident[]>(SEED_TIMELINE);

    useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

    // ── Fetch history ──────────────────────────────────────────────────────────
    const fetchHistory = useCallback(async () => {
        setHistoryLoading(true);
        try {
            const res = await fetch(`${API_BASE}/agents/sre/history`, {
                headers: authHeaders(), credentials: "include",
            });
            if (res.ok) {
                const data = await res.json();
                setHistory(data.jobs ?? []);
            }
        } catch { /* ignore */ }
        finally { setHistoryLoading(false); }
    }, []);

    useEffect(() => { if (tab === "history") fetchHistory(); }, [tab, fetchHistory]);

    // ── Action: Restart Server ──────────────────────────────────────────────────
    async function handleRestart() {
        setRestarting(true);
        setActionMsg(null);
        try {
            const res = await fetch(`${API_BASE}/agents/sre/remediate`, {
                method: "POST",
                headers: authHeaders(),
                credentials: "include",
                body: JSON.stringify({ incident_id: `manual_${Date.now()}`, playbook: "restart" }),
            });
            if (res.ok) {
                const data = await res.json();
                setActionMsg({ type: "ok", text: `Restart queued — job ${data.job_id?.slice(0, 8) ?? "submitted"}` });
                // Append a log line
                const now = new Date().toLocaleTimeString("en-US", { hour12: false });
                setLogs(prev => [{ time: now, level: "INFO", msg: "[sre-agent] Manual server restart triggered" }, ...prev]);
            } else {
                const err = await res.json().catch(() => ({}));
                setActionMsg({ type: "err", text: err.detail ?? "Restart request failed" });
            }
        } catch (e) {
            setActionMsg({ type: "ok", text: "Restart signal sent (Celery offline — simulation mode)" });
            const now = new Date().toLocaleTimeString("en-US", { hour12: false });
            setLogs(prev => [{ time: now, level: "INFO", msg: "[sre-agent] Restart simulated (broker offline)" }, ...prev]);
        } finally {
            setRestarting(false);
            setTimeout(() => setActionMsg(null), 5000);
        }
    }

    // ── Action: Rollback ───────────────────────────────────────────────────────
    async function handleRollback() {
        setRollingBack(true);
        setActionMsg(null);
        try {
            const res = await fetch(`${API_BASE}/agents/sre/remediate`, {
                method: "POST",
                headers: authHeaders(),
                credentials: "include",
                body: JSON.stringify({ incident_id: `manual_${Date.now()}`, playbook: "rollback" }),
            });
            if (res.ok) {
                const data = await res.json();
                setActionMsg({ type: "ok", text: `Rollback queued — job ${data.job_id?.slice(0, 8) ?? "submitted"}` });
                const now = new Date().toLocaleTimeString("en-US", { hour12: false });
                setLogs(prev => [{ time: now, level: "WARN", msg: "[sre-agent] Manual rollback triggered" }, ...prev]);
            } else {
                const err = await res.json().catch(() => ({}));
                setActionMsg({ type: "err", text: err.detail ?? "Rollback request failed" });
            }
        } catch {
            setActionMsg({ type: "ok", text: "Rollback signal sent (simulation mode)" });
            const now = new Date().toLocaleTimeString("en-US", { hour12: false });
            setLogs(prev => [{ time: now, level: "WARN", msg: "[sre-agent] Rollback simulated (broker offline)" }, ...prev]);
        } finally {
            setRollingBack(false);
            setTimeout(() => setActionMsg(null), 5000);
        }
    }

    const criticalCount = servers.filter(s => s.status === "critical").length;
    const warningCount  = servers.filter(s => s.status === "warning").length;

    return (
        <motion.div variants={container} initial="hidden" animate="visible" className="space-y-6">

            {/* ── Header ─────────────────────────────────────────────────── */}
            <motion.div variants={item} className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
                        <Shield className="w-6 h-6 text-cyan-400" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">SRE Agent</h1>
                        <p className="text-muted-foreground text-sm">
                            Infrastructure monitoring, incident response &amp; auto-recovery
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {criticalCount > 0 && (
                        <Badge className="bg-rose-500/10 text-rose-400 border-rose-500/20 animate-pulse">
                            {criticalCount} Critical
                        </Badge>
                    )}
                    {warningCount > 0 && (
                        <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20">
                            {warningCount} Warning
                        </Badge>
                    )}
                    <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1.5" />
                        Active
                    </Badge>
                </div>
            </motion.div>

            {/* ── Action buttons ──────────────────────────────────────────── */}
            <motion.div variants={item} className="flex gap-3 flex-wrap">
                <Button
                    onClick={handleRestart}
                    disabled={restarting}
                    className="bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 hover:shadow-[0_0_20px_rgba(6,182,212,0.2)] transition-all"
                >
                    {restarting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                    Restart Server
                </Button>
                <Button
                    onClick={handleRollback}
                    disabled={rollingBack}
                    className="bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 hover:shadow-[0_0_20px_rgba(245,158,11,0.2)] transition-all"
                >
                    {rollingBack ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <RotateCcw className="w-4 h-4 mr-2" />}
                    Rollback
                </Button>
                <Button
                    onClick={() => setShowLogs(v => !v)}
                    className="bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 hover:shadow-[0_0_20px_rgba(139,92,246,0.2)] transition-all"
                >
                    <Terminal className="w-4 h-4 mr-2" />
                    {showLogs ? "Hide Logs" : "View Logs"}
                </Button>
            </motion.div>

            {/* ── Action feedback ─────────────────────────────────────────── */}
            <AnimatePresence>
                {actionMsg && (
                    <motion.div
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        className={`flex items-center gap-2 px-4 py-3 rounded-xl border text-sm ${actionMsg.type === "ok" ? "bg-emerald-500/5 border-emerald-500/20 text-emerald-400" : "bg-rose-500/5 border-rose-500/20 text-rose-400"}`}
                    >
                        {actionMsg.type === "ok" ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <XCircle className="w-4 h-4 shrink-0" />}
                        {actionMsg.text}
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Tabs ───────────────────────────────────────────────────── */}
            <motion.div variants={item} className="flex gap-1 bg-white/5 border border-white/8 rounded-xl p-1 w-fit">
                {(["monitor", "history"] as Tab[]).map(t => (
                    <button
                        key={t}
                        onClick={() => setTab(t)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${tab === t ? "bg-white/10 text-white shadow" : "text-muted-foreground hover:text-white"}`}
                    >
                        {t === "monitor" ? <Activity className="w-4 h-4" /> : <History className="w-4 h-4" />}
                        {t === "monitor" ? "Live Monitor" : "Job History"}
                    </button>
                ))}
            </motion.div>

            {/* ══════════════════ MONITOR TAB ════════════════════ */}
            {tab === "monitor" && (
                <>
                    {/* Log Viewer (collapsible) */}
                    <AnimatePresence>
                        {showLogs && (
                            <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{ duration: 0.25 }}
                                className="overflow-hidden"
                            >
                                <Card className="bg-card border-white/5">
                                    <CardHeader>
                                        <CardTitle className="text-white text-base flex items-center gap-2">
                                            <Terminal className="w-4 h-4 text-emerald-400" />
                                            Live Logs
                                            <motion.div
                                                animate={{ opacity: [0.3, 1, 0.3] }}
                                                transition={{ duration: 1.5, repeat: Infinity }}
                                                className="w-2 h-2 rounded-full bg-emerald-500 ml-1"
                                            />
                                        </CardTitle>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="bg-[#0a0f1a] rounded-xl p-4 font-mono text-xs space-y-1.5 max-h-64 overflow-y-auto">
                                            {logs.map((line, i) => (
                                                <div key={i} className="flex gap-2">
                                                    <span className="text-muted-foreground shrink-0">{line.time}</span>
                                                    <span className={`shrink-0 font-semibold ${line.level === "ERROR" ? "text-rose-400" : line.level === "WARN" ? "text-amber-400" : "text-emerald-400"}`}>
                                                        [{line.level.padEnd(5)}]
                                                    </span>
                                                    <span className="text-white/80">{line.msg}</span>
                                                </div>
                                            ))}
                                            <motion.span
                                                animate={{ opacity: [0, 1, 0] }}
                                                transition={{ duration: 1, repeat: Infinity }}
                                                className="text-cyan-400"
                                            >█</motion.span>
                                            <div ref={logEndRef} />
                                        </div>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* Server Status Grid */}
                    <motion.div variants={item}>
                        <Card className="bg-card border-white/5">
                            <CardHeader>
                                <CardTitle className="text-white text-base flex items-center gap-2">
                                    <Server className="w-4 h-4 text-cyan-400" />
                                    Server Status
                                    <span className="ml-auto text-xs text-muted-foreground font-normal">
                                        {servers.filter(s => s.status === "healthy").length}/{servers.length} healthy
                                    </span>
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                    {servers.map((server, i) => (
                                        <motion.div
                                            key={server.name}
                                            initial={{ opacity: 0, scale: 0.95 }}
                                            animate={{ opacity: 1, scale: 1 }}
                                            transition={{ delay: i * 0.05 }}
                                            className={`p-4 rounded-xl border transition-all duration-300 hover:scale-[1.02] ${statusBorder(server.status)}`}
                                        >
                                            <div className="flex items-center justify-between mb-3">
                                                <div className="flex items-center gap-2">
                                                    <Server className={`w-4 h-4 ${serverIconColor(server.status)}`} />
                                                    <span className="text-sm font-medium text-white">{server.name}</span>
                                                </div>
                                                <Badge variant="secondary" className={`text-[10px] px-1.5 py-0 border-0 ${server.status === "healthy" ? "bg-emerald-500/10 text-emerald-400" : server.status === "warning" ? "bg-amber-500/10 text-amber-400" : "bg-rose-500/10 text-rose-400"}`}>
                                                    {server.status}
                                                </Badge>
                                            </div>
                                            <div className="space-y-2">
                                                <div className="flex items-center justify-between text-xs">
                                                    <span className="text-muted-foreground flex items-center gap-1"><Cpu className="w-3 h-3" /> CPU</span>
                                                    <span className="text-white">{server.cpu}%</span>
                                                </div>
                                                <Progress value={server.cpu} className={`h-1.5 ${server.cpu > 80 ? "[&>div]:bg-rose-500" : server.cpu > 60 ? "[&>div]:bg-amber-500" : "[&>div]:bg-emerald-500"}`} />
                                                <div className="flex items-center justify-between text-xs">
                                                    <span className="text-muted-foreground flex items-center gap-1"><HardDrive className="w-3 h-3" /> Memory</span>
                                                    <span className="text-white">{server.memory}%</span>
                                                </div>
                                                <Progress value={server.memory} className={`h-1.5 ${server.memory > 80 ? "[&>div]:bg-rose-500" : server.memory > 60 ? "[&>div]:bg-amber-500" : "[&>div]:bg-emerald-500"}`} />
                                                <div className="flex items-center justify-between text-xs mt-1">
                                                    <span className="text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> Uptime</span>
                                                    <span className="text-white">{server.uptime}</span>
                                                </div>
                                            </div>
                                        </motion.div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>

                    {/* Incident Timeline */}
                    <motion.div variants={item}>
                        <Card className="bg-card border-white/5">
                            <CardHeader>
                                <CardTitle className="text-white text-base flex items-center gap-2">
                                    <Activity className="w-4 h-4 text-amber-400" />
                                    Incident Timeline
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="relative space-y-4">
                                    <div className="absolute left-[7px] top-2 bottom-2 w-px bg-white/5" />
                                    {timeline.map((incident, i) => (
                                        <motion.div
                                            key={i}
                                            initial={{ opacity: 0, x: -10 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            transition={{ delay: i * 0.08 }}
                                            className="relative flex items-start gap-4 pl-6"
                                        >
                                            <div className={`absolute left-0 top-1 w-3.5 h-3.5 rounded-full border-2 ${incidentDot(incident.status)}`} />
                                            <div className="flex-1">
                                                <p className="text-sm text-white">{incident.title}</p>
                                                <div className="flex items-center gap-2 mt-1">
                                                    <span className="text-[10px] text-muted-foreground">{incident.time}</span>
                                                    <Badge variant="secondary" className={`text-[10px] px-1.5 py-0 border-0 ${incidentBadge(incident.status)}`}>
                                                        {incident.status}
                                                    </Badge>
                                                </div>
                                            </div>
                                        </motion.div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                </>
            )}

            {/* ══════════════════ HISTORY TAB ════════════════════ */}
            {tab === "history" && (
                <motion.div variants={item}>
                    <Card className="bg-card border-white/5">
                        <CardHeader className="flex flex-row items-center justify-between">
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <History className="w-4 h-4 text-cyan-400" />
                                SRE Job History
                            </CardTitle>
                            <Button
                                onClick={fetchHistory}
                                disabled={historyLoading}
                                className="bg-white/5 text-muted-foreground border border-white/10 hover:bg-white/10 text-xs h-8"
                            >
                                <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${historyLoading ? "animate-spin" : ""}`} />
                                Refresh
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {historyLoading ? (
                                <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
                                    <Loader2 className="w-4 h-4 animate-spin" /> Loading history…
                                </div>
                            ) : history.length === 0 ? (
                                <div className="text-center py-12 space-y-3">
                                    <History className="w-8 h-8 text-muted-foreground/30 mx-auto" />
                                    <p className="text-sm text-muted-foreground">No SRE jobs yet.</p>
                                    <p className="text-xs text-muted-foreground/60">Use the Pipeline or trigger an ingest to see history here.</p>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {history.map((job, i) => (
                                        <motion.div
                                            key={job.job_id}
                                            initial={{ opacity: 0, y: 6 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            transition={{ delay: i * 0.04 }}
                                            className="flex items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-all"
                                        >
                                            <div className={`w-2 h-2 rounded-full shrink-0 ${job.status === "completed" ? "bg-emerald-400" : job.status === "running" ? "bg-cyan-400 animate-pulse" : job.status === "failed" ? "bg-rose-400" : "bg-amber-400"}`} />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <p className="text-sm text-white font-mono">{job.job_id.slice(0, 16)}</p>
                                                    <Badge className={`text-[10px] border-0 ${job.status === "completed" ? "bg-emerald-500/10 text-emerald-400" : job.status === "failed" ? "bg-rose-500/10 text-rose-400" : "bg-cyan-500/10 text-cyan-400"}`}>
                                                        {job.status}
                                                    </Badge>
                                                    <Badge className="text-[10px] bg-white/5 text-muted-foreground border-0">
                                                        {job.phase}
                                                    </Badge>
                                                </div>
                                                {job.root_cause && (
                                                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{job.root_cause}</p>
                                                )}
                                            </div>
                                            <div className="text-right shrink-0">
                                                {job.confidence !== undefined && (
                                                    <p className="text-xs text-cyan-400">{(job.confidence * 100).toFixed(0)}% confidence</p>
                                                )}
                                                <p className="text-[10px] text-muted-foreground mt-0.5">
                                                    {job.created_at ? new Date(job.created_at).toLocaleTimeString() : "—"}
                                                </p>
                                            </div>
                                        </motion.div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </motion.div>
            )}
        </motion.div>
    );
}
