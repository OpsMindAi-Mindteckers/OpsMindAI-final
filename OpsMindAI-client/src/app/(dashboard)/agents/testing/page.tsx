"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    TestTube2,
    CheckCircle2,
    XCircle,
    Clock,
    Play,
    BarChart3,
    ChevronDown,
    ChevronRight,
    RotateCw,
    RefreshCw,
    Activity,
    GitBranch,
    Shield,
    Zap,
    AlertTriangle,
    ArrowRight,
    Terminal,
    Cpu,
    FileText,
    FlaskConical,
    Bug,
    TrendingUp,
    Info,
    History,
    FileCode2,
    Database,
    Loader2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// ── Types ─────────────────────────────────────────────────────────────────────

type Tab = "standalone" | "history";
type Phase = "generate" | "suite" | "regression";
type Framework = "pytest" | "jest";
type TriggerType = "incident" | "deploy" | "manual";
type RegressionTestType = "incident" | "load" | "db_perf";

interface CoverageBreakdown {
    coverage_pct:   number;
    delta_pct:      number;
    lines_covered:  number;
    lines_total:    number;
    gate_passed:    boolean;
    threshold:      number;
    previous_pct?:  number;
}

interface GeneratedFileSummary {
    source_file:         string;
    output_file:         string;
    functions_processed: number;
    tokens_used:         number;
    model_used:          string;
}

interface JobStatus {
    job_id:                 string;
    status:                 string;
    phase?:                 string;
    error?:                 string;
    created_at?:            string;
    completed_at?:          string;
    duration_s?:            number;
    generated_files?:       GeneratedFileSummary[];
    warnings?:              string[];
    coverage?:              CoverageBreakdown;
    gate_passed?:           boolean;
    output_file?:           string;
    incident_tests_count?:  number;
    load_tests_count?:      number;
    db_perf_tests_count?:   number;
    tokens_used?:           number;
    model_used?:            string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const container = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.07 } } };
const item      = { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } };

function authHeaders(): Record<string, string> {
    const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function PhaseTab({ phase, active, label, icon: Icon, onClick }: {
    phase: Phase; active: Phase; label: string; icon: React.ElementType; onClick: () => void;
}) {
    const isActive = phase === active;
    const colors: Record<Phase, string> = { generate: "#8b5cf6", suite: "#06b6d4", regression: "#f59e0b" };
    const color = colors[phase];
    return (
        <button
            onClick={onClick}
            className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium transition-all"
            style={{
                color: isActive ? color : "#64748b",
                borderBottom: isActive ? `2px solid ${color}` : "2px solid transparent",
            }}
        >
            <Icon className="w-4 h-4" />
            {label}
        </button>
    );
}

function StatusBadge({ status }: { status: string }) {
    const map: Record<string, string> = {
        completed: "bg-emerald-500/10 text-emerald-400",
        failed:    "bg-rose-500/10 text-rose-400",
        running:   "bg-cyan-500/10 text-cyan-400",
        queued:    "bg-amber-500/10 text-amber-400",
    };
    return (
        <Badge className={`text-[10px] border-0 ${map[status] ?? "bg-white/5 text-muted-foreground"}`}>
            {status}
        </Badge>
    );
}

function CoverageBar({ coverage }: { coverage: CoverageBreakdown }) {
    const pct       = coverage.coverage_pct;
    const threshold = coverage.threshold * 100;
    const passed    = coverage.gate_passed;
    return (
        <div className="space-y-4">
            <div className={`p-4 rounded-xl border flex items-center gap-3 ${passed ? "bg-emerald-500/5 border-emerald-500/20" : "bg-rose-500/5 border-rose-500/20"}`}>
                {passed
                    ? <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                    : <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0" />}
                <span className={`text-sm font-semibold ${passed ? "text-emerald-400" : "text-rose-400"}`}>
                    Coverage Gate {passed ? "Passed" : "Failed"}
                </span>
            </div>

            <div className="space-y-2">
                <div className="flex items-end gap-3">
                    <span className={`text-4xl font-bold ${passed ? "text-emerald-400" : "text-rose-400"}`}>
                        {pct.toFixed(1)}%
                    </span>
                    <div className="pb-1 text-xs text-muted-foreground space-y-0.5">
                        <p>threshold: {threshold.toFixed(0)}%</p>
                        {coverage.previous_pct !== undefined && (
                            <p>prev: {coverage.previous_pct.toFixed(1)}% ({coverage.delta_pct >= 0 ? "+" : ""}{coverage.delta_pct.toFixed(1)}%)</p>
                        )}
                    </div>
                </div>
                <div className="relative h-2 rounded-full bg-white/5 overflow-visible">
                    <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(pct, 100)}%` }}
                        transition={{ duration: 1, ease: "easeOut" }}
                        className="h-full rounded-full"
                        style={{ background: passed ? "linear-gradient(90deg,#10b981,#06b6d4)" : "linear-gradient(90deg,#f43f5e,#f59e0b)" }}
                    />
                    <div
                        className="absolute top-1/2 -translate-y-1/2 w-px h-4 bg-white/40"
                        style={{ left: `${threshold}%` }}
                    />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5">
                    <p className="text-xs text-muted-foreground">Lines Covered</p>
                    <p className="text-xl font-bold text-emerald-400 mt-0.5">{coverage.lines_covered.toLocaleString()}</p>
                </div>
                <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5">
                    <p className="text-xs text-muted-foreground">Total Lines</p>
                    <p className="text-xl font-bold text-white mt-0.5">{coverage.lines_total.toLocaleString()}</p>
                </div>
            </div>
        </div>
    );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TestingAgentPage() {
    const [tab, setTab]     = useState<Tab>("standalone");
    const [phase, setPhase] = useState<Phase>("generate");

    // Phase 1
    const [genRepo, setGenRepo]           = useState("");
    const [genBranch, setGenBranch]       = useState("main");
    const [genFilePath, setGenFilePath]   = useState("");
    const [genFramework, setGenFramework] = useState<Framework>("pytest");
    const [genThreshold, setGenThreshold] = useState(80);
    const [genPrNumber, setGenPrNumber]   = useState("");
    const [genLoading, setGenLoading]     = useState(false);
    const [genJob, setGenJob]             = useState<JobStatus | null>(null);
    const [genError, setGenError]         = useState<string | null>(null);
    const [expandedFile, setExpandedFile] = useState<string | null>(null);

    // Phase 2
    const [suiteJobId, setSuiteJobId]     = useState("");
    const [suiteLoading, setSuiteLoading] = useState(false);
    const [suiteJob, setSuiteJob]         = useState<JobStatus | null>(null);
    const [suiteError, setSuiteError]     = useState<string | null>(null);

    // Phase 3
    const [regRepo, setRegRepo]             = useState("");
    const [regBranch, setRegBranch]         = useState("main");
    const [regTrigger, setRegTrigger]       = useState<TriggerType>("incident");
    const [regIncidentId, setRegIncidentId] = useState("");
    const [regTestType, setRegTestType]     = useState<RegressionTestType>("incident");
    const [regLoading, setRegLoading]       = useState(false);
    const [regJob, setRegJob]               = useState<JobStatus | null>(null);
    const [regError, setRegError]           = useState<string | null>(null);

    // History
    const [history, setHistory]               = useState<JobStatus[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);

    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    function pollJob(jobId: string, onUpdate: (j: JobStatus) => void, onDone: () => void) {
        let attempts = 0;
        const id = setInterval(async () => {
            attempts++;
            if (attempts > 120) { clearInterval(id); onDone(); return; }
            try {
                const res = await fetch(`${API_BASE}/agents/testing/jobs/${jobId}`, {
                    headers: authHeaders(), credentials: "include",
                });
                if (!res.ok) return;
                const data: JobStatus = await res.json();
                onUpdate(data);
                if (data.status === "completed" || data.status === "failed") {
                    clearInterval(id); onDone();
                }
            } catch { /* keep polling */ }
        }, 3000);
        pollRef.current = id;
    }

    useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

    async function handleGenerate() {
        if (!genRepo.trim()) return;
        setGenLoading(true); setGenJob(null); setGenError(null);
        try {
            const res = await fetch(`${API_BASE}/agents/testing/generate`, {
                method: "POST", headers: authHeaders(), credentials: "include",
                body: JSON.stringify({
                    repo_url:           genRepo.trim(),
                    branch:             genBranch || "main",
                    file_path:          genFilePath.trim() || undefined,
                    framework:          genFramework,
                    coverage_threshold: genThreshold / 100,
                    pr_number:          genPrNumber ? parseInt(genPrNumber) : undefined,
                }),
            });
            const data = await res.json();
            if (!res.ok) { setGenError(data.detail ?? "Failed to submit"); setGenLoading(false); return; }
            setSuiteJobId(data.job_id);
            pollJob(data.job_id, j => setGenJob(j), () => setGenLoading(false));
        } catch (e) { setGenError(String(e)); setGenLoading(false); }
    }

    async function handleSuite() {
        if (!suiteJobId.trim()) return;
        setSuiteLoading(true); setSuiteJob(null); setSuiteError(null);
        try {
            const res = await fetch(`${API_BASE}/agents/testing/suite`, {
                method: "POST", headers: authHeaders(), credentials: "include",
                body: JSON.stringify({ generation_job_id: suiteJobId.trim() }),
            });
            const data = await res.json();
            if (!res.ok) { setSuiteError(data.detail ?? "Failed to submit"); setSuiteLoading(false); return; }
            pollJob(data.job_id, j => setSuiteJob(j), () => setSuiteLoading(false));
        } catch (e) { setSuiteError(String(e)); setSuiteLoading(false); }
    }

    async function handleRegression() {
        if (!regRepo.trim()) return;
        setRegLoading(true); setRegJob(null); setRegError(null);
        try {
            const res = await fetch(`${API_BASE}/agents/testing/regression`, {
                method: "POST", headers: authHeaders(), credentials: "include",
                body: JSON.stringify({
                    repo_url: regRepo.trim(),
                    branch:   regBranch || "main",
                    trigger_event: {
                        type:        regTrigger,
                        test_type:   regTestType,
                        incident_id: regIncidentId.trim() || undefined,
                    },
                }),
            });
            const data = await res.json();
            if (!res.ok) { setRegError(data.detail ?? "Failed to submit"); setRegLoading(false); return; }
            pollJob(data.job_id, j => setRegJob(j), () => setRegLoading(false));
        } catch (e) { setRegError(String(e)); setRegLoading(false); }
    }

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
        } catch { setHistory([]); }
        finally { setHistoryLoading(false); }
    }, []);

    useEffect(() => { if (tab === "history") fetchHistory(); }, [tab, fetchHistory]);

    // ── Render ────────────────────────────────────────────────────────────────

    return (
        <motion.div variants={container} initial="hidden" animate="visible" className="space-y-6">
            {/* Header */}
            <motion.div variants={item} className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                    <TestTube2 className="w-6 h-6 text-violet-400" />
                </div>
                <div>
                    <h1 className="text-2xl font-bold text-white">Testing Agent</h1>
                    <p className="text-muted-foreground text-sm">Generate test stubs, enforce coverage gates &amp; build regression suites</p>
                </div>
            </motion.div>

            {/* ── STANDALONE TAB ─────────────────────────────────────────────── */}

            {/* ── STANDALONE TAB ─────────────────────────────────────────────── */}
            {tab === "standalone" && (
                <motion.div variants={item} className="space-y-4">
                    <Card className="bg-card border-white/5">
                        {/* Phase sub-tabs */}
                        <div className="flex border-b border-white/5 px-2">
                            <PhaseTab phase="generate"   active={phase} label="Phase 1 — Generate"   icon={FileCode2} onClick={() => setPhase("generate")} />
                            <PhaseTab phase="suite"      active={phase} label="Phase 2 — Suite"       icon={BarChart3} onClick={() => setPhase("suite")} />
                            <PhaseTab phase="regression" active={phase} label="Phase 3 — Regression"  icon={Zap}       onClick={() => setPhase("regression")} />
                        </div>

                        <CardContent className="p-6 space-y-5">

                            {/* ── PHASE 1: GENERATE ─────────────────────────── */}
                            {phase === "generate" && (
                                <>
                                    <div>
                                        <h3 className="text-white font-semibold flex items-center gap-2 mb-1">
                                            <FileCode2 className="w-4 h-4 text-violet-400" />
                                            Phase 1 — Repository Analysis &amp; Test Generation
                                        </h3>
                                        <p className="text-xs text-muted-foreground">Clone the repo, analyse source files with the LLM, and write test stubs. Leave File Path empty to scan the entire repo.</p>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div className="md:col-span-2 space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Repository URL <span className="text-rose-400">*</span></Label>
                                            <Input
                                                value={genRepo}
                                                onChange={e => setGenRepo(e.target.value)}
                                                placeholder="https://github.com/org/repo"
                                                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 h-10"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Branch</Label>
                                            <Input
                                                value={genBranch}
                                                onChange={e => setGenBranch(e.target.value)}
                                                placeholder="main"
                                                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 h-10"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">File Path (optional)</Label>
                                            <Input
                                                value={genFilePath}
                                                onChange={e => setGenFilePath(e.target.value)}
                                                placeholder="src/services/auth.py"
                                                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 h-10"
                                            />
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Framework</Label>
                                            <div className="flex gap-2">
                                                {(["pytest", "jest"] as Framework[]).map(f => (
                                                    <button
                                                        key={f}
                                                        onClick={() => setGenFramework(f)}
                                                        className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-all ${genFramework === f ? "bg-violet-500/15 border-violet-500/40 text-violet-300" : "bg-white/[0.03] border-white/8 text-muted-foreground hover:text-white"}`}
                                                    >{f}</button>
                                                ))}
                                            </div>
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Coverage Gate: <span className="text-violet-400 font-mono">{genThreshold}%</span></Label>
                                            <input
                                                type="range" min={0} max={100} value={genThreshold}
                                                onChange={e => setGenThreshold(Number(e.target.value))}
                                                className="w-full accent-violet-500 h-2 mt-2"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">PR Number (optional)</Label>
                                            <Input
                                                value={genPrNumber}
                                                onChange={e => setGenPrNumber(e.target.value)}
                                                placeholder="42"
                                                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 h-10"
                                            />
                                        </div>
                                    </div>

                                    {genError && (
                                        <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/5 border border-rose-500/20 text-rose-400 text-sm">
                                            <XCircle className="w-4 h-4 shrink-0" /> {genError}
                                        </div>
                                    )}

                                    <Button
                                        onClick={handleGenerate}
                                        disabled={genLoading || !genRepo.trim()}
                                        className="bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 transition-all"
                                    >
                                        {genLoading
                                            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Generating…</>
                                            : <><Play className="w-4 h-4 mr-2" />Generate Tests</>}
                                    </Button>

                                    <AnimatePresence>
                                        {genJob && (
                                            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3 pt-2 border-t border-white/5">
                                                <div className="flex items-center justify-between flex-wrap gap-2">
                                                    <div className="flex items-center gap-2">
                                                        {(genJob.status === "running" || genJob.status === "queued")
                                                            ? <RotateCw className="w-4 h-4 animate-spin text-violet-400" />
                                                            : genJob.status === "completed"
                                                                ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                                                : <XCircle className="w-4 h-4 text-rose-400" />}
                                                        <span className="text-sm text-white font-mono">{genJob.job_id}</span>
                                                        <StatusBadge status={genJob.status} />
                                                    </div>
                                                    {genJob.duration_s != null && (
                                                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                                                            <Clock className="w-3 h-3" /> {genJob.duration_s.toFixed(1)}s
                                                        </span>
                                                    )}
                                                </div>

                                                {genJob.status === "completed" && genJob.generated_files && genJob.generated_files.length > 0 && (
                                                    <div className="space-y-2">
                                                        <p className="text-xs text-muted-foreground font-mono">{genJob.generated_files.length} file(s) generated</p>
                                                        {genJob.generated_files.map((f, i) => (
                                                            <div key={i}>
                                                                <button
                                                                    onClick={() => setExpandedFile(expandedFile === f.source_file ? null : f.source_file)}
                                                                    className="w-full flex items-center gap-2 p-3 rounded-xl bg-white/[0.03] border border-white/5 hover:border-white/10 transition-all text-left"
                                                                >
                                                                    {expandedFile === f.source_file
                                                                        ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                                                                        : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />}
                                                                    <FileCode2 className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                                                                    <span className="text-xs text-white font-mono flex-1 truncate">{f.source_file}</span>
                                                                    <span className="text-[10px] text-muted-foreground">{f.functions_processed} fn · {f.tokens_used} tok</span>
                                                                </button>
                                                                <AnimatePresence>
                                                                    {expandedFile === f.source_file && (
                                                                        <motion.div
                                                                            initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                                                                            className="ml-6 mt-1 p-3 rounded-xl bg-white/[0.02] border border-white/5 overflow-hidden"
                                                                        >
                                                                            <p className="text-[10px] text-muted-foreground">Output: <span className="text-cyan-400 font-mono">{f.output_file}</span></p>
                                                                            <p className="text-[10px] text-muted-foreground mt-0.5">Model: <span className="text-violet-400 font-mono">{f.model_used}</span></p>
                                                                        </motion.div>
                                                                    )}
                                                                </AnimatePresence>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}

                                                {genJob.warnings && genJob.warnings.length > 0 && (
                                                    <div className="space-y-1">
                                                        {genJob.warnings.map((w, i) => (
                                                            <p key={i} className="text-[11px] text-amber-400 flex items-center gap-1.5">
                                                                <AlertTriangle className="w-3 h-3 shrink-0" /> {w}
                                                            </p>
                                                        ))}
                                                    </div>
                                                )}

                                                {genJob.status === "completed" && (
                                                    <Button
                                                        onClick={() => { setPhase("suite"); setSuiteJobId(genJob.job_id); }}
                                                        className="bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all text-sm"
                                                    >
                                                        Proceed to Phase 2 — Run Suite →
                                                    </Button>
                                                )}
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </>
                            )}

                            {/* ── PHASE 2: SUITE ────────────────────────────── */}
                            {phase === "suite" && (
                                <>
                                    <div>
                                        <h3 className="text-white font-semibold flex items-center gap-2 mb-1">
                                            <BarChart3 className="w-4 h-4 text-cyan-400" />
                                            Phase 2 — Run Test Suite &amp; Enforce Coverage Gate
                                        </h3>
                                        <p className="text-xs text-muted-foreground">Execute the generated tests, parse coverage, and enforce the gate. Requires a completed Phase 1 job.</p>
                                    </div>

                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">Generation Job ID <span className="text-rose-400">*</span></Label>
                                        <div className="relative">
                                            <GitBranch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                            <Input
                                                value={suiteJobId}
                                                onChange={e => setSuiteJobId(e.target.value)}
                                                placeholder="testgen_xxxxxxxx"
                                                className="pl-10 bg-white/5 border-white/10 text-white placeholder:text-white/20 h-10 font-mono"
                                            />
                                        </div>
                                        <p className="text-[11px] text-muted-foreground">Paste the job_id from Phase 1, or complete Phase 1 first to auto-fill.</p>
                                    </div>

                                    {suiteError && (
                                        <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/5 border border-rose-500/20 text-rose-400 text-sm">
                                            <XCircle className="w-4 h-4 shrink-0" /> {suiteError}
                                        </div>
                                    )}

                                    <Button
                                        onClick={handleSuite}
                                        disabled={suiteLoading || !suiteJobId.trim()}
                                        className="bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all"
                                    >
                                        {suiteLoading
                                            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Running…</>
                                            : <><Play className="w-4 h-4 mr-2" />Run Test Suite</>}
                                    </Button>

                                    <AnimatePresence>
                                        {suiteJob && (
                                            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4 pt-2 border-t border-white/5">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    {(suiteJob.status === "running" || suiteJob.status === "queued")
                                                        ? <RotateCw className="w-4 h-4 animate-spin text-cyan-400" />
                                                        : suiteJob.status === "completed"
                                                            ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                                            : <XCircle className="w-4 h-4 text-rose-400" />}
                                                    <span className="text-sm text-white font-mono">{suiteJob.job_id}</span>
                                                    <StatusBadge status={suiteJob.status} />
                                                    {suiteJob.duration_s != null && (
                                                        <span className="text-xs text-muted-foreground flex items-center gap-1 ml-auto">
                                                            <Clock className="w-3 h-3" /> {suiteJob.duration_s.toFixed(1)}s
                                                        </span>
                                                    )}
                                                </div>
                                                {suiteJob.coverage && <CoverageBar coverage={suiteJob.coverage} />}
                                                {suiteJob.status === "completed" && !suiteJob.coverage && (
                                                    <p className="text-sm text-muted-foreground">Suite completed — no coverage data returned.</p>
                                                )}
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </>
                            )}

                            {/* ── PHASE 3: REGRESSION ───────────────────────── */}
                            {phase === "regression" && (
                                <>
                                    <div>
                                        <h3 className="text-white font-semibold flex items-center gap-2 mb-1">
                                            <Zap className="w-4 h-4 text-amber-400" />
                                            Phase 3 — Build Regression Suite
                                        </h3>
                                        <p className="text-xs text-muted-foreground">Generate incident-driven regression tests, load/stress scenarios, and DB perf assertions. Provide a repo URL directly — independent of Phase 1.</p>
                                    </div>

                                    <div className="grid grid-cols-3 gap-3">
                                        {([
                                            { key: "incident", label: "Incident Tests", icon: AlertTriangle, desc: "Prevent recurrence of past incidents" },
                                            { key: "load",     label: "Load Tests",     icon: Zap,           desc: "Stress scenarios for affected endpoints" },
                                            { key: "db_perf",  label: "DB Perf Tests",  icon: Database,      desc: "Database performance assertions" },
                                        ] as { key: RegressionTestType; label: string; icon: React.ElementType; desc: string }[]).map(t => (
                                            <button
                                                key={t.key}
                                                onClick={() => setRegTestType(t.key)}
                                                className={`p-4 rounded-xl border text-left transition-all ${regTestType === t.key ? "bg-amber-500/10 border-amber-500/30" : "bg-white/[0.02] border-white/5 hover:border-white/15"}`}
                                            >
                                                <t.icon className={`w-4 h-4 mb-2 ${regTestType === t.key ? "text-amber-400" : "text-muted-foreground"}`} />
                                                <p className="text-xs font-medium text-white">{t.label}</p>
                                                <p className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{t.desc}</p>
                                            </button>
                                        ))}
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div className="md:col-span-2 space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Repository URL <span className="text-rose-400">*</span></Label>
                                            <Input
                                                value={regRepo}
                                                onChange={e => setRegRepo(e.target.value)}
                                                placeholder="https://github.com/org/repo"
                                                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 h-10"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Branch</Label>
                                            <Input
                                                value={regBranch}
                                                onChange={e => setRegBranch(e.target.value)}
                                                placeholder="main"
                                                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 h-10"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Incident ID (optional)</Label>
                                            <Input
                                                value={regIncidentId}
                                                onChange={e => setRegIncidentId(e.target.value)}
                                                placeholder="inc_abc123"
                                                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 h-10"
                                            />
                                        </div>
                                    </div>

                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">Trigger Type</Label>
                                        <div className="flex gap-2">
                                            {(["incident", "deploy", "manual"] as TriggerType[]).map(t => (
                                                <button
                                                    key={t}
                                                    onClick={() => setRegTrigger(t)}
                                                    className={`px-4 py-2 rounded-lg text-sm font-medium border transition-all ${regTrigger === t ? "bg-amber-500/15 border-amber-500/40 text-amber-300" : "bg-white/[0.03] border-white/8 text-muted-foreground hover:text-white"}`}
                                                >{t}</button>
                                            ))}
                                        </div>
                                    </div>

                                    {regError && (
                                        <div className="flex items-center gap-2 p-3 rounded-xl bg-rose-500/5 border border-rose-500/20 text-rose-400 text-sm">
                                            <XCircle className="w-4 h-4 shrink-0" /> {regError}
                                        </div>
                                    )}

                                    <Button
                                        onClick={handleRegression}
                                        disabled={regLoading || !regRepo.trim()}
                                        className="bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all"
                                    >
                                        {regLoading
                                            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Building…</>
                                            : <><Play className="w-4 h-4 mr-2" />Build Regression Suite</>}
                                    </Button>

                                    <AnimatePresence>
                                        {regJob && (
                                            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-3 pt-2 border-t border-white/5">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    {(regJob.status === "running" || regJob.status === "queued")
                                                        ? <RotateCw className="w-4 h-4 animate-spin text-amber-400" />
                                                        : regJob.status === "completed"
                                                            ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                                            : <XCircle className="w-4 h-4 text-rose-400" />}
                                                    <span className="text-sm text-white font-mono">{regJob.job_id}</span>
                                                    <StatusBadge status={regJob.status} />
                                                </div>

                                                {regJob.status === "completed" && (
                                                    <div className="grid grid-cols-3 gap-3">
                                                        {[
                                                            { label: "Incident Tests", val: regJob.incident_tests_count ?? 0, color: "text-rose-400" },
                                                            { label: "Load Tests",     val: regJob.load_tests_count ?? 0,     color: "text-amber-400" },
                                                            { label: "DB Perf Tests",  val: regJob.db_perf_tests_count ?? 0,  color: "text-cyan-400" },
                                                        ].map(s => (
                                                            <div key={s.label} className="p-3 rounded-xl bg-white/[0.03] border border-white/5 text-center">
                                                                <p className={`text-xl font-bold ${s.color}`}>{s.val}</p>
                                                                <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}

                                                {regJob.output_file && (
                                                    <p className="text-xs text-muted-foreground">
                                                        Output: <span className="text-cyan-400 font-mono">{regJob.output_file}</span>
                                                    </p>
                                                )}
                                                {regJob.model_used && (
                                                    <p className="text-xs text-muted-foreground">
                                                        Model: <span className="text-violet-400 font-mono">{regJob.model_used}</span>
                                                        {regJob.tokens_used ? ` · ${regJob.tokens_used.toLocaleString()} tokens` : ""}
                                                    </p>
                                                )}
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </>
                            )}

                            {/* How It Works */}
                            <div className="pt-4 border-t border-white/5">
                                <p className="text-xs text-muted-foreground mb-3">How It Works</p>
                                <div className="grid grid-cols-3 gap-3">
                                    {[
                                        { phase: "Phase 1", label: "Generate Tests",  color: "#8b5cf6", steps: ["Clone repo & scan files", "Extract function signatures via AST", "LLM generates test stubs"] },
                                        { phase: "Phase 2", label: "Run Suite",        color: "#06b6d4", steps: ["Execute pytest/jest", "Parse coverage XML/JSON", "Enforce coverage gate"] },
                                        { phase: "Phase 3", label: "Regression Suite", color: "#f59e0b", steps: ["Load incident history from RAG", "Generate anti-regression tests", "Build load/stress scenarios"] },
                                    ].map((p, i) => (
                                        <div key={i} className="p-3 rounded-xl border border-white/5 bg-white/[0.02] space-y-2">
                                            <div className="flex items-center gap-2">
                                                <span className="text-[10px] font-mono px-2 py-0.5 rounded" style={{ background: `${p.color}15`, color: p.color }}>{p.phase}</span>
                                                <span className="text-[11px] text-white font-medium">{p.label}</span>
                                            </div>
                                            <ol className="space-y-1">
                                                {p.steps.map((s, j) => (
                                                    <li key={j} className="text-[10px] text-muted-foreground flex items-start gap-1.5">
                                                        <span style={{ color: p.color }} className="font-mono shrink-0">{j + 1}</span>
                                                        {s}
                                                    </li>
                                                ))}
                                            </ol>
                                        </div>
                                    ))}
                                </div>
                            </div>

                        </CardContent>
                    </Card>
                </motion.div>
            )}

            {/* ── HISTORY TAB ────────────────────────────────────────────────── */}
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
                                                    <p className="text-sm text-white font-mono">{job.job_id.slice(0, 20)}</p>
                                                    <StatusBadge status={job.status} />
                                                    {job.phase && (
                                                        <Badge className="text-[10px] bg-white/5 text-muted-foreground border-0">{job.phase}</Badge>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="text-right shrink-0">
                                                {job.coverage !== undefined && (
                                                    <p className="text-xs text-violet-400">
                                                        {typeof job.coverage === "object"
                                                            ? `${job.coverage.coverage_pct.toFixed(0)}% coverage`
                                                            : `${(job.coverage as number * 100).toFixed(0)}% coverage`}
                                                    </p>
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
