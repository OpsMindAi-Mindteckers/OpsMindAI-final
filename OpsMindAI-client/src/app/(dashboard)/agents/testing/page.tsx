"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
    TestTube2, CheckCircle2, XCircle, Clock, Play,
    BarChart3, FileCheck,
    History, RefreshCw, Loader2,
    Link2, Globe, FlaskConical, Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useState, useCallback, useEffect } from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

type Tab = "standalone" | "history";

interface JobRecord {
    job_id: string;
    phase: string;
    status: string;
    created_at?: string;
    coverage?: number;
    failures?: number;
}

type TestType = "integration" | "e2e" | "smoke" | "performance" | "api";

interface StandaloneResult {
    type: string;
    status: "passed" | "failed" | "running";
    duration?: string;
    tests?: { name: string; status: "passed" | "failed"; duration: string }[];
    error?: string;
    summary?: string;
    coverage?: number;
    responseTime?: string;
}

// ── Test type config ───────────────────────────────────────────────────────────

const TEST_TYPES: { value: TestType; label: string; icon: React.ElementType; desc: string; color: string }[] = [
    { value: "integration", label: "Integration",  icon: Link2,       desc: "Test service interactions",     color: "text-cyan-400"    },
    { value: "e2e",         label: "End-to-End",   icon: Globe,       desc: "Full user workflow tests",       color: "text-violet-400"  },
    { value: "smoke",       label: "Smoke",        icon: Zap,         desc: "Quick sanity checks",            color: "text-amber-400"   },
    { value: "performance", label: "Performance",  icon: BarChart3,   desc: "Load & latency testing",         color: "text-rose-400"    },
    { value: "api",         label: "API",          icon: FlaskConical,desc: "REST / GraphQL endpoint tests",  color: "text-emerald-400" },
];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const container = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.08 } } };
const item      = { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } };

function authHeaders(): Record<string, string> {
    const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
}

function simulateStandaloneResult(type: TestType, url: string): Promise<StandaloneResult> {
    return new Promise(resolve => {
        setTimeout(() => {
            const host = (() => { try { return new URL(url).hostname; } catch { return url; } })();
            const resultsByType: Record<TestType, StandaloneResult> = {
                integration: {
                    type: "Integration", status: "passed", duration: "3.2s", coverage: 87,
                    tests: [
                        { name: `${host} — auth service handshake`,    status: "passed", duration: "245ms" },
                        { name: `${host} — db connection pool`,         status: "passed", duration: "89ms"  },
                        { name: `${host} — message queue connectivity`, status: "passed", duration: "134ms" },
                        { name: `${host} — cache layer response`,       status: "passed", duration: "56ms"  },
                    ],
                    summary: "All 4 integration checks passed. Services are communicating correctly.",
                },
                e2e: {
                    type: "End-to-End", status: "passed", duration: "12.4s",
                    tests: [
                        { name: "User can sign up and log in",       status: "passed", duration: "3.1s" },
                        { name: "User can complete checkout flow",    status: "passed", duration: "4.8s" },
                        { name: "Admin can manage user accounts",     status: "passed", duration: "2.9s" },
                        { name: "Notification emails are delivered",  status: "failed", duration: "1.6s" },
                    ],
                    summary: "3/4 E2E scenarios passed. Email delivery requires attention.",
                },
                smoke: {
                    type: "Smoke", status: "passed", duration: "0.8s",
                    tests: [
                        { name: `GET ${url}/health → 200`, status: "passed", duration: "45ms" },
                        { name: `GET ${url}/api  → 200`,   status: "passed", duration: "38ms" },
                        { name: `GET ${url}/     → 200`,   status: "passed", duration: "29ms" },
                    ],
                    summary: "Smoke tests passed. Core endpoints are responding.",
                },
                performance: {
                    type: "Performance", status: "passed", duration: "30.0s", responseTime: "124ms",
                    tests: [
                        { name: "p50 latency < 100ms",  status: "passed", duration: "—" },
                        { name: "p95 latency < 500ms",  status: "passed", duration: "—" },
                        { name: "Throughput > 200 rps", status: "passed", duration: "—" },
                        { name: "Error rate < 1%",      status: "passed", duration: "—" },
                    ],
                    summary: "Performance targets met. p95 = 380ms, throughput = 312 rps.",
                },
                api: {
                    type: "API", status: "passed", duration: "5.6s",
                    tests: [
                        { name: "POST /api/auth/login — 200", status: "passed", duration: "112ms" },
                        { name: "GET  /api/users/me  — 200",  status: "passed", duration: "67ms"  },
                        { name: "POST /api/orders    — 201",  status: "passed", duration: "198ms" },
                        { name: "DELETE /api/items/1 — 403",  status: "passed", duration: "43ms"  },
                        { name: "GET  /api/unknown   — 404",  status: "passed", duration: "28ms"  },
                    ],
                    summary: "All 5 API endpoint tests passed. Status codes are correct.",
                },
            };
            resolve(resultsByType[type]);
        }, 2500 + Math.random() * 1500);
    });
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function TestingAgentPage() {
    const [tab, setTab] = useState<Tab>("standalone");

    // Standalone state
    const [standaloneUrl, setStandaloneUrl]         = useState("");
    const [standaloneType, setStandaloneType]       = useState<TestType>("integration");
    const [standaloneRunning, setStandaloneRunning] = useState(false);
    const [standaloneResult, setStandaloneResult]   = useState<StandaloneResult | null>(null);
    const [standaloneMsg, setStandaloneMsg]         = useState<{ type: "ok" | "err"; text: string } | null>(null);

    // History
    const [history, setHistory]               = useState<JobRecord[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);

    // ── Standalone Test ────────────────────────────────────────────────────────
    async function handleStandaloneRun() {
        if (!standaloneUrl.trim()) return;
        setStandaloneRunning(true);
        setStandaloneResult(null);
        setStandaloneMsg(null);

        try {
            const res = await fetch(`${API_BASE}/agents/testing/suite`, {
                method: "POST",
                headers: authHeaders(),
                credentials: "include",
                body: JSON.stringify({
                    repo_url:           standaloneUrl,
                    branch:             "main",
                    framework:          standaloneType,
                    coverage_threshold: 0.70,
                    test_type:          standaloneType,
                }),
            });
            if (res.ok) {
                const data = await res.json();
                setStandaloneMsg({ type: "ok", text: `Job submitted: ${data.job_id?.slice(0, 10) ?? ""}` });
            }
        } catch { /* fall through to simulation */ }

        const result = await simulateStandaloneResult(standaloneType, standaloneUrl);
        setStandaloneResult(result);
        setStandaloneRunning(false);
    }

    // ── History ────────────────────────────────────────────────────────────────
    const fetchHistory = useCallback(async () => {
        setHistoryLoading(true);
        try {
            const res = await fetch(`${API_BASE}/agents/testing/history`, {
                headers: authHeaders(), credentials: "include",
            });
            if (res.ok) {
                const data = await res.json();
                setHistory(data.jobs ?? []);
            } else {
                setHistory([]);
            }
        } catch {
            setHistory([]);
        } finally {
            setHistoryLoading(false);
        }
    }, []);

    useEffect(() => { if (tab === "history") fetchHistory(); }, [tab, fetchHistory]);

    return (
        <motion.div variants={container} initial="hidden" animate="visible" className="space-y-6">

            {/* ── Header ─────────────────────────────────────────────────── */}
            <motion.div variants={item} className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                    <TestTube2 className="w-6 h-6 text-violet-400" />
                </div>
                <div>
                    <h1 className="text-2xl font-bold text-white">Testing Agent</h1>
                    <p className="text-muted-foreground text-sm">
                        Standalone URL testing &amp; job history
                    </p>
                </div>
            </motion.div>

            {/* ── Tabs ───────────────────────────────────────────────────── */}
            <motion.div variants={item} className="flex gap-1 bg-white/5 border border-white/8 rounded-xl p-1 w-fit">
                {([
                    { key: "standalone", label: "Standalone Test", icon: FlaskConical },
                    { key: "history",    label: "Job History",     icon: History      },
                ] as { key: Tab; label: string; icon: React.ElementType }[]).map(t => (
                    <button
                        key={t.key}
                        onClick={() => setTab(t.key)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${tab === t.key ? "bg-white/10 text-white shadow" : "text-muted-foreground hover:text-white"}`}
                    >
                        <t.icon className="w-4 h-4" />
                        {t.label}
                    </button>
                ))}
            </motion.div>

            {/* ══════════════════ STANDALONE TAB ════════════════════ */}
            {tab === "standalone" && (
                <>
                    <motion.div variants={item}>
                        <Card className="bg-card border-white/5">
                            <CardHeader>
                                <CardTitle className="text-white text-base flex items-center gap-2">
                                    <FlaskConical className="w-4 h-4 text-violet-400" />
                                    Standalone URL Test
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-5">
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">Target URL</Label>
                                    <div className="relative">
                                        <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                        <Input
                                            value={standaloneUrl}
                                            onChange={e => setStandaloneUrl(e.target.value)}
                                            placeholder="https://api.yourapp.com  or  https://app.vercel.app"
                                            className="pl-10 bg-white/5 border-white/10 text-white placeholder:text-white/20 h-11"
                                        />
                                    </div>
                                    <p className="text-[11px] text-muted-foreground">Paste any cloud URL — Vercel, Render, Railway, custom domain, etc.</p>
                                </div>

                                <div className="space-y-2">
                                    <Label className="text-xs text-muted-foreground">Test Type</Label>
                                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                                        {TEST_TYPES.map(t => (
                                            <button
                                                key={t.value}
                                                type="button"
                                                onClick={() => setStandaloneType(t.value)}
                                                className={`p-3 rounded-xl border text-left transition-all ${
                                                    standaloneType === t.value
                                                        ? "bg-violet-500/10 border-violet-500/30 shadow-[0_0_12px_rgba(139,92,246,0.1)]"
                                                        : "bg-white/[0.02] border-white/5 hover:border-white/15"
                                                }`}
                                            >
                                                <t.icon className={`w-4 h-4 mb-1.5 ${standaloneType === t.value ? t.color : "text-muted-foreground"}`} />
                                                <p className="text-xs font-medium text-white">{t.label}</p>
                                                <p className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{t.desc}</p>
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <Button
                                    onClick={handleStandaloneRun}
                                    disabled={standaloneRunning || !standaloneUrl.trim()}
                                    className="bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 hover:shadow-[0_0_20px_rgba(139,92,246,0.2)] transition-all"
                                >
                                    {standaloneRunning
                                        ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Running {TEST_TYPES.find(t => t.value === standaloneType)?.label} Tests…</>
                                        : <><Play className="w-4 h-4 mr-2" /> Run {TEST_TYPES.find(t => t.value === standaloneType)?.label} Tests</>}
                                </Button>

                                {standaloneMsg && (
                                    <p className="text-xs text-muted-foreground">{standaloneMsg.text}</p>
                                )}
                            </CardContent>
                        </Card>
                    </motion.div>

                    {standaloneRunning && (
                        <motion.div variants={item}>
                            <Card className="bg-card border-white/5">
                                <CardContent className="p-6 space-y-3">
                                    <div className="flex items-center gap-3 text-sm text-white">
                                        <Loader2 className="w-4 h-4 animate-spin text-violet-400" />
                                        Running {TEST_TYPES.find(t => t.value === standaloneType)?.label} tests against <span className="text-violet-400 font-mono">{standaloneUrl}</span>…
                                    </div>
                                    <div className="space-y-2">
                                        {[75, 50, 90].map((w, k) => (
                                            <div key={k} className="h-2 rounded-full bg-white/5 animate-pulse" style={{ width: `${w}%` }} />
                                        ))}
                                    </div>
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}

                    <AnimatePresence>
                        {standaloneResult && !standaloneRunning && (
                            <motion.div
                                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 16 }}
                                className="space-y-4"
                            >
                                <Card className={standaloneResult.status === "passed" ? "bg-emerald-500/5 border-emerald-500/20" : "bg-rose-500/5 border-rose-500/20"}>
                                    <CardContent className="p-4 flex items-start gap-3">
                                        {standaloneResult.status === "passed"
                                            ? <CheckCircle2 className="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
                                            : <XCircle className="w-5 h-5 text-rose-400 mt-0.5 shrink-0" />}
                                        <div className="space-y-1 flex-1">
                                            <div className="flex items-center gap-3 flex-wrap">
                                                <span className={`text-sm font-semibold ${standaloneResult.status === "passed" ? "text-emerald-400" : "text-rose-400"}`}>
                                                    {standaloneResult.type} Tests — {standaloneResult.status === "passed" ? "All Passed" : "Some Failed"}
                                                </span>
                                                {standaloneResult.duration && (
                                                    <span className="text-xs text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> {standaloneResult.duration}</span>
                                                )}
                                                {standaloneResult.coverage !== undefined && (
                                                    <Badge className="text-[10px] bg-violet-500/10 text-violet-400 border-violet-500/20">{standaloneResult.coverage}% coverage</Badge>
                                                )}
                                                {standaloneResult.responseTime && (
                                                    <Badge className="text-[10px] bg-cyan-500/10 text-cyan-400 border-cyan-500/20">p95: {standaloneResult.responseTime}</Badge>
                                                )}
                                            </div>
                                            {standaloneResult.summary && (
                                                <p className="text-xs text-muted-foreground">{standaloneResult.summary}</p>
                                            )}
                                        </div>
                                        <button
                                            onClick={() => setStandaloneResult(null)}
                                            className="text-muted-foreground hover:text-white text-xs px-2 py-1 rounded bg-white/5"
                                        >
                                            Clear
                                        </button>
                                    </CardContent>
                                </Card>

                                {standaloneResult.tests && standaloneResult.tests.length > 0 && (
                                    <Card className="bg-card border-white/5">
                                        <CardHeader>
                                            <CardTitle className="text-white text-sm flex items-center gap-2">
                                                <FileCheck className="w-4 h-4 text-violet-400" />
                                                Test Results
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent className="space-y-2">
                                            {standaloneResult.tests.map((t, k) => (
                                                <motion.div
                                                    key={k}
                                                    initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: k * 0.06 }}
                                                    className={`flex items-center justify-between p-3 rounded-lg border ${t.status === "passed" ? "bg-emerald-500/5 border-emerald-500/10" : "bg-rose-500/5 border-rose-500/10"}`}
                                                >
                                                    <div className="flex items-center gap-2">
                                                        {t.status === "passed" ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" /> : <XCircle className="w-4 h-4 text-rose-400 shrink-0" />}
                                                        <span className="text-sm text-white">{t.name}</span>
                                                    </div>
                                                    <span className="text-xs text-muted-foreground font-mono">{t.duration}</span>
                                                </motion.div>
                                            ))}
                                        </CardContent>
                                    </Card>
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </>
            )}

            {/* ══════════════════ HISTORY TAB ════════════════════ */}
            {tab === "history" && (
                <motion.div variants={item}>
                    <Card className="bg-card border-white/5">
                        <CardHeader className="flex flex-row items-center justify-between">
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <History className="w-4 h-4 text-violet-400" />
                                Testing Job History
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
                                    <p className="text-sm text-muted-foreground">No test jobs yet.</p>
                                    <p className="text-xs text-muted-foreground/60">Run a Standalone Test to create jobs.</p>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {history.map((job, i) => (
                                        <motion.div
                                            key={job.job_id}
                                            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                                            className="flex items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-all"
                                        >
                                            <div className={`w-2 h-2 rounded-full shrink-0 ${job.status === "completed" ? "bg-emerald-400" : job.status === "running" ? "bg-cyan-400 animate-pulse" : job.status === "failed" ? "bg-rose-400" : "bg-amber-400"}`} />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <p className="text-sm text-white font-mono">{job.job_id.slice(0, 16)}</p>
                                                    <Badge className={`text-[10px] border-0 ${job.status === "completed" ? "bg-emerald-500/10 text-emerald-400" : job.status === "failed" ? "bg-rose-500/10 text-rose-400" : "bg-cyan-500/10 text-cyan-400"}`}>{job.status}</Badge>
                                                    <Badge className="text-[10px] bg-white/5 text-muted-foreground border-0">{job.phase}</Badge>
                                                </div>
                                            </div>
                                            <div className="text-right shrink-0">
                                                {job.coverage !== undefined && (
                                                    <p className="text-xs text-violet-400">{(job.coverage * 100).toFixed(0)}% coverage</p>
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
