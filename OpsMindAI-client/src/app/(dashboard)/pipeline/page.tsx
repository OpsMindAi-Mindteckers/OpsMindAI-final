"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
    GitBranch,
    Server,
    Activity,
    Shield,
    Code2,
    TestTube2,
    Rocket,
    CheckCircle2,
    Clock,
    XCircle,
    Loader2,
    Zap,
    Link2,
    FileText,
    ChevronDown,
    ChevronUp,
    RotateCcw,
    Play,
    SkipForward,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useEffect, useRef, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────────

type InputMode = "url" | "log";

type StageStatus = "pending" | "running" | "completed" | "failed" | "skipped";

interface StageInfo {
    id:          string;
    label:       string;
    shortLabel:  string;
    icon:        React.ElementType;
    description: string;
}

interface PipelineEvent {
    timestamp: string;
    stage:     string;
    status:    string;
    message:   string;
    details:   Record<string, unknown>;
}

interface PipelineState {
    pipeline_id:   string;
    status:        string;
    current_stage: string | null;
    stages:        Record<string, StageStatus>;
    service:       string;
    error?:        string;
    started_at?:   string;
    completed_at?: string;
}

// ── Stage definitions ──────────────────────────────────────────────────────────

const STAGES: StageInfo[] = [
    {
        id:          "sre_monitor",
        label:       "SRE Monitor & RCA",
        shortLabel:  "SRE Monitor",
        icon:        Shield,
        description: "Ingests alert or log, runs root-cause analysis, classifies bug vs infra issue",
    },
    {
        id:          "testing_initial",
        label:       "Testing Agent",
        shortLabel:  "Initial Tests",
        icon:        TestTube2,
        description: "Runs full test suite against current codebase to surface failures",
    },
    {
        id:          "code_refactor",
        label:       "Code Refactor",
        shortLabel:  "Refactor",
        icon:        Code2,
        description: "Detects code smells and bugs, generates patches, opens PR",
    },
    {
        id:          "testing_verify",
        label:       "Testing Agent",
        shortLabel:  "Verify Fixes",
        icon:        TestTube2,
        description: "Re-runs test suite to confirm all code fixes pass",
    },
    {
        id:          "sre_remediate",
        label:       "SRE Remediate",
        shortLabel:  "Remediate",
        icon:        Server,
        description: "Executes remediation playbook and restarts the server",
    },
];

// ── Color / style maps ─────────────────────────────────────────────────────────

const stageColor = (status: StageStatus) => {
    switch (status) {
        case "running":   return { node: "bg-cyan-500/15 border-cyan-500/50 shadow-[0_0_20px_rgba(6,182,212,0.35)]", text: "text-cyan-400", badge: "bg-cyan-500/10 text-cyan-400" };
        case "completed": return { node: "bg-emerald-500/10 border-emerald-500/40", text: "text-emerald-400", badge: "bg-emerald-500/10 text-emerald-400" };
        case "failed":    return { node: "bg-red-500/10 border-red-500/40",         text: "text-red-400",     badge: "bg-red-500/10 text-red-400" };
        case "skipped":   return { node: "bg-white/5 border-white/10",              text: "text-slate-500",   badge: "bg-white/5 text-slate-500" };
        default:          return { node: "bg-white/3 border-white/8",               text: "text-slate-600",   badge: "bg-white/5 text-slate-600" };
    }
};

const statusIcon = (status: StageStatus, size = "w-5 h-5") => {
    switch (status) {
        case "running":   return <Loader2      className={`${size} text-cyan-400 animate-spin`} />;
        case "completed": return <CheckCircle2 className={`${size} text-emerald-400`} />;
        case "failed":    return <XCircle      className={`${size} text-red-400`} />;
        case "skipped":   return <SkipForward  className={`${size} text-slate-500`} />;
        default:          return <Clock        className={`${size} text-slate-600`} />;
    }
};

const eventDot = (status: string) => {
    switch (status) {
        case "completed": return "bg-emerald-400";
        case "failed":    return "bg-red-400";
        case "started":
        case "progress":  return "bg-cyan-400";
        case "skipped":   return "bg-slate-500";
        default:          return "bg-amber-400";
    }
};

// ── Animations ─────────────────────────────────────────────────────────────────

const container = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.08 } } };
const item      = { hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0 } };

// ── API_BASE ───────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

// ── Component ──────────────────────────────────────────────────────────────────

export default function PipelinePage() {
    // Input state
    const [inputMode, setInputMode]     = useState<InputMode>("url");
    const [serverUrl, setServerUrl]     = useState("");
    const [logText, setLogText]         = useState("");
    const [repoUrl, setRepoUrl]         = useState("");
    const [showAdvanced, setShowAdvanced] = useState(false);

    // Pipeline run state
    const [pipelineId, setPipelineId]   = useState<string | null>(null);
    const [pipelineState, setPipelineState] = useState<PipelineState | null>(null);
    const [events, setEvents]           = useState<PipelineEvent[]>([]);
    const [submitting, setSubmitting]   = useState(false);
    const [running, setRunning]         = useState(false);
    const [error, setError]             = useState<string | null>(null);

    const esRef          = useRef<EventSource | null>(null);
    const logEndRef      = useRef<HTMLDivElement>(null);
    const [selectedStage, setSelectedStage] = useState<string>(STAGES[0].id);

    // Scroll log to bottom on new events
    useEffect(() => {
        logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [events]);

    // Close SSE on unmount
    useEffect(() => () => { esRef.current?.close(); }, []);

    const connectSSE = useCallback((pid: string) => {
        esRef.current?.close();
        const es = new EventSource(`${API_BASE}/agents/pipeline/stream/${pid}`);
        esRef.current = es;

        es.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data) as Record<string, unknown>;

                if (msg.type === "state") {
                    setPipelineState(msg.data as PipelineState);
                    return;
                }
                if (msg.type === "done") {
                    setRunning(false);
                    es.close();
                    return;
                }
                if (msg.type === "error") {
                    setError(String(msg.message ?? "Stream error"));
                    setRunning(false);
                    es.close();
                    return;
                }

                // Regular event
                const ev = msg as unknown as PipelineEvent;
                setEvents(prev => [...prev, ev]);

                // Update stage statuses from event
                if (ev.stage && ev.stage !== "pipeline") {
                    setPipelineState(prev => {
                        if (!prev) return prev;
                        const newStages = { ...prev.stages };
                        if (ev.status === "started")   newStages[ev.stage] = "running";
                        if (ev.status === "completed") newStages[ev.stage] = "completed";
                        if (ev.status === "failed")    newStages[ev.stage] = "failed";
                        if (ev.status === "skipped")   newStages[ev.stage] = "skipped";
                        return {
                            ...prev,
                            stages:        newStages,
                            current_stage: ev.status === "started" ? ev.stage : prev.current_stage,
                        };
                    });
                    if (ev.status === "started") setSelectedStage(ev.stage);
                }

                // Terminal
                if (ev.stage === "pipeline" && (ev.status === "completed" || ev.status === "failed")) {
                    setPipelineState(prev => prev ? { ...prev, status: ev.status } : prev);
                    setRunning(false);
                    es.close();
                }
            } catch { /* ignore malformed */ }
        };

        es.onerror = () => {
            setError("Lost connection to pipeline stream.");
            setRunning(false);
            es.close();
        };
    }, []);

    const handleSubmit = async () => {
        const value = inputMode === "url" ? serverUrl.trim() : logText.trim();
        if (!value) { setError("Paste a server URL or log text first."); return; }

        setError(null);
        setSubmitting(true);
        setEvents([]);
        setPipelineState(null);
        setPipelineId(null);

        try {
            const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
            const res = await fetch(`${API_BASE}/agents/pipeline/run`, {
                method:  "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                credentials: "include",
                body: JSON.stringify({
                    input_type: inputMode,
                    server_url: inputMode === "url" ? value : undefined,
                    raw_log:    inputMode === "log" ? value : undefined,
                    repo_url:   repoUrl.trim() || undefined,
                }),
            });

            const json = await res.json();
            if (!res.ok) {
                setError(json.detail ?? "Failed to start pipeline.");
                return;
            }

            const pid: string = json.pipeline_id;
            setPipelineId(pid);
            setRunning(true);
            setPipelineState({
                pipeline_id:   pid,
                status:        "queued",
                current_stage: null,
                stages: {
                    sre_monitor:     "pending",
                    testing_initial: "pending",
                    code_refactor:   "pending",
                    testing_verify:  "pending",
                    sre_remediate:   "pending",
                },
                service: "",
            });
            connectSSE(pid);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Network error");
        } finally {
            setSubmitting(false);
        }
    };

    const handleReset = () => {
        esRef.current?.close();
        setPipelineId(null);
        setPipelineState(null);
        setEvents([]);
        setRunning(false);
        setError(null);
        setServerUrl("");
        setLogText("");
    };

    const overallStatus = pipelineState?.status ?? "idle";
    const currentStageInfo = STAGES.find(s => s.id === selectedStage)!;
    const selectedStageStatus: StageStatus = pipelineState?.stages?.[selectedStage] ?? "pending";
    const selectedColors = stageColor(selectedStageStatus);

    return (
        <motion.div variants={container} initial="hidden" animate="visible" className="space-y-6">

            {/* ── Header ─────────────────────────────────────────────────── */}
            <motion.div variants={item} className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                        <GitBranch className="w-6 h-6 text-amber-400" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">Autonomous Pipeline</h1>
                        <p className="text-muted-foreground text-sm">
                            Paste a server URL or log — agents handle the rest end-to-end
                        </p>
                    </div>
                </div>
                {pipelineId && (
                    <Button
                        onClick={handleReset}
                        className="bg-white/5 text-white border border-white/10 hover:bg-white/10"
                    >
                        <RotateCcw className="w-4 h-4 mr-2" />
                        New Run
                    </Button>
                )}
            </motion.div>

            {/* ── Input card (shown only when not running) ───────────────── */}
            {!pipelineId && (
                <motion.div variants={item}>
                    <Card className="bg-card border-white/8">
                        <CardHeader>
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <Zap className="w-4 h-4 text-amber-400" />
                                Trigger Pipeline
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {/* Mode toggle */}
                            <div className="flex gap-2">
                                <button
                                    onClick={() => setInputMode("url")}
                                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${inputMode === "url" ? "bg-amber-500/15 border border-amber-500/30 text-amber-400" : "bg-white/5 border border-white/10 text-muted-foreground hover:text-white"}`}
                                >
                                    <Link2 className="w-4 h-4" /> Server URL
                                </button>
                                <button
                                    onClick={() => setInputMode("log")}
                                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${inputMode === "log" ? "bg-amber-500/15 border border-amber-500/30 text-amber-400" : "bg-white/5 border border-white/10 text-muted-foreground hover:text-white"}`}
                                >
                                    <FileText className="w-4 h-4" /> Paste Log
                                </button>
                            </div>

                            {/* Main input */}
                            {inputMode === "url" ? (
                                <Input
                                    value={serverUrl}
                                    onChange={e => setServerUrl(e.target.value)}
                                    placeholder="https://myapp.vercel.app  |  https://myservice.onrender.com  |  https://..."
                                    className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground font-mono text-sm"
                                />
                            ) : (
                                <textarea
                                    value={logText}
                                    onChange={e => setLogText(e.target.value)}
                                    rows={8}
                                    placeholder={"Paste your server log here…\n\nERROR: TypeError: Cannot read property 'map' of undefined\n  at handler (/app/api/users.js:42:18)\n  ..."}
                                    className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder:text-muted-foreground font-mono text-xs resize-y focus:outline-none focus:border-cyan-500/50"
                                />
                            )}

                            {/* Advanced options */}
                            <button
                                onClick={() => setShowAdvanced(v => !v)}
                                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-white transition-colors"
                            >
                                {showAdvanced ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                                Advanced options (optional)
                            </button>

                            <AnimatePresence>
                                {showAdvanced && (
                                    <motion.div
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: "auto", opacity: 1 }}
                                        exit={{ height: 0, opacity: 0 }}
                                        className="overflow-hidden"
                                    >
                                        <div className="pt-2 space-y-3">
                                            <div>
                                                <label className="text-xs text-muted-foreground mb-1 block">
                                                    GitHub repo URL <span className="text-slate-600">(enables code refactor stage)</span>
                                                </label>
                                                <Input
                                                    value={repoUrl}
                                                    onChange={e => setRepoUrl(e.target.value)}
                                                    placeholder="https://github.com/org/repo"
                                                    className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground font-mono text-sm"
                                                />
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {error && (
                                <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                                    {error}
                                </p>
                            )}

                            <Button
                                onClick={handleSubmit}
                                disabled={submitting}
                                className="w-full bg-amber-500/15 text-amber-400 border border-amber-500/30 hover:bg-amber-500/25 transition-all"
                            >
                                {submitting ? (
                                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Starting…</>
                                ) : (
                                    <><Play className="w-4 h-4 mr-2" /> Run Autonomous Pipeline</>
                                )}
                            </Button>
                        </CardContent>
                    </Card>
                </motion.div>
            )}

            {/* ── Pipeline visualisation ─────────────────────────────────── */}
            {pipelineState && (
                <motion.div variants={item}>
                    <Card className="bg-card border-white/5 overflow-hidden">
                        <CardContent className="p-8">
                            {/* Overall status bar */}
                            <div className="flex items-center justify-between mb-8">
                                <div className="flex items-center gap-3">
                                    {overallStatus === "running" && <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />}
                                    {overallStatus === "completed" && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
                                    {overallStatus === "failed" && <XCircle className="w-4 h-4 text-red-400" />}
                                    {overallStatus === "queued" && <Clock className="w-4 h-4 text-amber-400" />}
                                    <span className="text-sm text-muted-foreground font-mono">
                                        {pipelineId}
                                    </span>
                                </div>
                                <Badge className={`text-[11px] ${overallStatus === "completed" ? "bg-emerald-500/10 text-emerald-400" : overallStatus === "failed" ? "bg-red-500/10 text-red-400" : overallStatus === "running" ? "bg-cyan-500/10 text-cyan-400" : "bg-white/5 text-muted-foreground"} border-0`}>
                                    {overallStatus}
                                </Badge>
                            </div>

                            {/* Stage nodes */}
                            <div className="relative flex items-start justify-between">
                                {/* Connector track */}
                                <div className="absolute top-8 left-8 right-8 h-0.5 bg-white/5 z-0" />

                                {STAGES.map((stage, i) => {
                                    const sstatus: StageStatus = pipelineState.stages?.[stage.id] ?? "pending";
                                    const colors    = stageColor(sstatus);
                                    const isActive  = selectedStage === stage.id;

                                    return (
                                        <div key={stage.id} className="relative z-10 flex flex-col items-center cursor-pointer group" onClick={() => setSelectedStage(stage.id)}>
                                            {/* Progress connector */}
                                            {i > 0 && (
                                                <div className="absolute top-8 right-full w-full h-0.5 -mr-px">
                                                    {sstatus === "completed" && <div className="h-full bg-emerald-500/50" />}
                                                    {sstatus === "running" && (
                                                        <motion.div
                                                            className="h-full bg-gradient-to-r from-emerald-500/40 to-cyan-500/60"
                                                            animate={{ opacity: [0.4, 1, 0.4] }}
                                                            transition={{ duration: 1.8, repeat: Infinity }}
                                                        />
                                                    )}
                                                </div>
                                            )}

                                            <motion.div
                                                animate={sstatus === "running" ? {
                                                    boxShadow: ["0 0 0px rgba(6,182,212,0)", "0 0 24px rgba(6,182,212,0.5)", "0 0 0px rgba(6,182,212,0)"],
                                                } : {}}
                                                transition={sstatus === "running" ? { duration: 1.8, repeat: Infinity } : {}}
                                                className={`w-16 h-16 rounded-2xl border-2 flex items-center justify-center transition-all duration-300 ${colors.node} ${isActive ? "ring-2 ring-offset-2 ring-offset-[#030712] ring-white/10 scale-110" : "group-hover:scale-105"}`}
                                            >
                                                <stage.icon className={`w-7 h-7 ${colors.text}`} />
                                            </motion.div>

                                            <span className={`mt-3 text-[11px] font-medium text-center max-w-[80px] leading-tight ${colors.text}`}>
                                                {stage.shortLabel}
                                            </span>

                                            <div className="mt-1.5">
                                                {statusIcon(sstatus, "w-3.5 h-3.5")}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            )}

            {/* ── Stage detail + event log ───────────────────────────────── */}
            {pipelineState && (
                <motion.div variants={item} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {/* Selected stage card */}
                    <Card className={`bg-card border transition-all duration-300 ${selectedColors.node.includes("cyan") ? "border-cyan-500/30" : selectedColors.node.includes("emerald") ? "border-emerald-500/30" : selectedColors.node.includes("red") ? "border-red-500/30" : "border-white/8"}`}>
                        <CardHeader>
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <currentStageInfo.icon className={`w-5 h-5 ${selectedColors.text}`} />
                                {currentStageInfo.label}
                                <Badge className={`ml-auto text-[10px] border-0 ${selectedColors.badge}`}>
                                    {selectedStageStatus}
                                </Badge>
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <p className="text-sm text-muted-foreground">{currentStageInfo.description}</p>

                            {/* Stage-specific details from last relevant event */}
                            {(() => {
                                const stageEvents = events.filter(e => e.stage === selectedStage);
                                const lastDetails = stageEvents.slice().reverse().find(e => Object.keys(e.details).length > 0)?.details ?? {};
                                if (!Object.keys(lastDetails).length) return null;
                                return (
                                    <div className="grid grid-cols-2 gap-2">
                                        {Object.entries(lastDetails).map(([k, v]) => (
                                            <div key={k} className="p-3 rounded-lg bg-white/5 border border-white/5">
                                                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{k.replace(/_/g, " ")}</p>
                                                <p className="text-sm font-medium text-white mt-0.5 truncate">{String(v)}</p>
                                            </div>
                                        ))}
                                    </div>
                                );
                            })()}

                            {selectedStageStatus === "running" && (
                                <div className="flex items-center gap-2 text-xs text-cyan-400">
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    Processing…
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Live event log */}
                    <Card className="bg-card border-white/5">
                        <CardHeader>
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <Activity className="w-4 h-4 text-amber-400" />
                                Live Event Log
                                {running && (
                                    <span className="ml-auto flex items-center gap-1.5 text-xs text-cyan-400">
                                        <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                                        Streaming
                                    </span>
                                )}
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                                <AnimatePresence initial={false}>
                                    {events.length === 0 && (
                                        <p className="text-xs text-muted-foreground py-4 text-center">
                                            Waiting for events…
                                        </p>
                                    )}
                                    {events.map((ev, i) => (
                                        <motion.div
                                            key={i}
                                            initial={{ opacity: 0, x: -8 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            className="flex items-start gap-3 p-2 rounded-lg hover:bg-white/5 transition-colors"
                                        >
                                            <span className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${eventDot(ev.status)}`} />
                                            <div className="min-w-0">
                                                <p className="text-sm text-white leading-snug">{ev.message}</p>
                                                <div className="flex items-center gap-2 mt-0.5">
                                                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-white/5 text-muted-foreground border-0">
                                                        {ev.stage}
                                                    </Badge>
                                                    <span className="text-[10px] text-muted-foreground font-mono">
                                                        {new Date(ev.timestamp).toLocaleTimeString()}
                                                    </span>
                                                </div>
                                            </div>
                                        </motion.div>
                                    ))}
                                </AnimatePresence>
                                <div ref={logEndRef} />
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            )}

            {/* ── Completion banner ──────────────────────────────────────── */}
            <AnimatePresence>
                {overallStatus === "completed" && (
                    <motion.div
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        variants={item}
                    >
                        <Card className="bg-emerald-500/5 border border-emerald-500/25">
                            <CardContent className="flex items-center gap-4 p-5">
                                <CheckCircle2 className="w-8 h-8 text-emerald-400 shrink-0" />
                                <div>
                                    <p className="text-white font-semibold">Pipeline completed successfully</p>
                                    <p className="text-sm text-muted-foreground mt-0.5">
                                        All agents ran, code was fixed, tests passed, and the server was restarted.
                                    </p>
                                </div>
                                <Button onClick={handleReset} className="ml-auto bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 shrink-0">
                                    <RotateCcw className="w-4 h-4 mr-2" /> New Run
                                </Button>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {overallStatus === "failed" && (
                    <motion.div
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0 }}
                        variants={item}
                    >
                        <Card className="bg-red-500/5 border border-red-500/25">
                            <CardContent className="flex items-center gap-4 p-5">
                                <XCircle className="w-8 h-8 text-red-400 shrink-0" />
                                <div>
                                    <p className="text-white font-semibold">Pipeline failed</p>
                                    <p className="text-sm text-muted-foreground mt-0.5">
                                        {pipelineState?.error ?? "An error occurred during the pipeline run."}
                                    </p>
                                </div>
                                <Button onClick={handleReset} className="ml-auto bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 shrink-0">
                                    <RotateCcw className="w-4 h-4 mr-2" /> Retry
                                </Button>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── How-it-works (shown only before first run) ─────────────── */}
            {!pipelineId && (
                <motion.div variants={item}>
                    <Card className="bg-card border-white/5">
                        <CardHeader>
                            <CardTitle className="text-white text-sm flex items-center gap-2">
                                <Rocket className="w-4 h-4 text-amber-400" />
                                How the pipeline works
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                                {STAGES.map((s, i) => (
                                    <div key={s.id} className="flex flex-col items-center text-center gap-2 p-3 rounded-lg bg-white/3 border border-white/5">
                                        <div className="w-9 h-9 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
                                            <s.icon className="w-4 h-4 text-muted-foreground" />
                                        </div>
                                        <div>
                                            <p className="text-[11px] font-semibold text-white">{i + 1}. {s.shortLabel}</p>
                                            <p className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{s.description}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            )}
        </motion.div>
    );
}
