"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
    Code2, Bug, Sparkles, FileCode, GitCompare,
    ArrowRight, RotateCw, CheckCircle2, AlertTriangle,
    ExternalLink, RefreshCw, ChevronDown, ChevronRight,
    Play, Cpu, Activity, History, Loader2, Clock,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useRefactor } from "@/lib/hooks/use-refactor";

// ── Types ──────────────────────────────────────────────────────────────────────

type MainTab = "standalone" | "history";
type Step    = "idle" | "analyzing" | "polling" | "suggesting" | "done";

interface RefactorJob {
    job_id: string;
    status: string;
    phase: string;
    created_at?: string;
    completed_at?: string;
    duration_s?: number;
    error?: string;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const OPENROUTER_FREE_MODELS = [
    { id: "deepseek/deepseek-v4-flash:free",           label: "DeepSeek V4 Flash",    provider: "DeepSeek"      },
    { id: "qwen/qwen3-coder:free",                     label: "Qwen3 Coder",          provider: "Qwen"          },
    { id: "meta-llama/llama-3.3-70b-instruct:free",    label: "Llama 3.3 70B",        provider: "Meta"          },
    { id: "meta-llama/llama-3.2-3b-instruct:free",     label: "Llama 3.2 3B",         provider: "Meta"          },
    { id: "google/gemma-4-31b-it:free",                label: "Gemma 4 31B",          provider: "Google"        },
    { id: "google/gemma-4-26b-a4b-it:free",            label: "Gemma 4 26B MoE",      provider: "Google"        },
    { id: "nvidia/nemotron-3-super-120b-a12b:free",     label: "Nemotron Super 120B",  provider: "NVIDIA"        },
    { id: "openai/gpt-oss-120b:free",                  label: "GPT OSS 120B",         provider: "OpenAI"        },
    { id: "openai/gpt-oss-20b:free",                   label: "GPT OSS 20B",          provider: "OpenAI"        },
    { id: "nousresearch/hermes-3-llama-3.1-405b:free", label: "Hermes 3 405B",        provider: "NousResearch"  },
    { id: "minimax/minimax-m2.5:free",                 label: "MiniMax M2.5",         provider: "MiniMax"       },
    { id: "arcee-ai/trinity-large-thinking:free",      label: "Trinity Thinking",     provider: "Arcee AI"      },
];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const containerVariants = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.08 } } };
const itemVariants       = { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } };

// ── Helpers ────────────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
    const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
}

function statusColor(status: string) {
    switch (status?.toLowerCase()) {
        case "active":
        case "completed": return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
        case "running":   return "bg-cyan-500/10 text-cyan-400 border-cyan-500/20";
        case "idle":
        case "pending":   return "bg-amber-500/10 text-amber-400 border-amber-500/20";
        case "error":
        case "failed":    return "bg-rose-500/10 text-rose-400 border-rose-500/20";
        default:          return "bg-white/5 text-muted-foreground border-white/10";
    }
}

function statusDot(status: string) {
    switch (status?.toLowerCase()) {
        case "active":
        case "completed": return "bg-emerald-400";
        case "running":   return "bg-cyan-400 animate-pulse";
        case "idle":
        case "pending":   return "bg-amber-400";
        case "failed":    return "bg-rose-400";
        default:          return "bg-white/30";
    }
}

function relTime(iso?: string): string {
    if (!iso) return "—";
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1)  return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function CodeRefactorPage() {
    const {
        agents, agentsLoading, fetchAgents,
        jobId, jobStatus,
        suggestLoading, suggestions, suggestJobId,
        applyLoading, prUrl,
        error,
        analyze, pollJob, suggest, apply, reset,
    } = useRefactor();

    const [mainTab, setMainTab]             = useState<MainTab>("standalone");
    const [step, setStep]                   = useState<Step>("idle");
    const [expandedSuggestion, setExpanded] = useState<number | null>(null);

    const [repoUrl, setRepoUrl]                     = useState("");
    const [branch, setBranch]                       = useState("master");
    const [severityThreshold, setSeverityThreshold] = useState("medium");
    const [selectedModel, setSelectedModel]         = useState(OPENROUTER_FREE_MODELS[0].id);

    // History
    const [history, setHistory]               = useState<RefactorJob[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);

    const isRunning     = step === "analyzing" || step === "polling" || step === "suggesting";
    const smellCount    = jobStatus?.smells?.length ?? jobStatus?.changes_summary?.smells_detected ?? 0;
    const suggestionList = suggestions?.suggestions ?? [];

    // ── Standalone analysis ────────────────────────────────────────────────────

    async function handleAnalyze() {
        if (!repoUrl.trim()) return;
        setStep("analyzing");
        const result = await analyze({ repo_url: repoUrl, branch, file_paths: [], severity_threshold: severityThreshold, model: selectedModel });
        if (!result?.job_id) { setStep("idle"); return; }
        setStep("polling");
        const jobResult = await pollJob(result.job_id);
        if (!jobResult || jobResult.status === "failed" || jobResult.status === "error") { setStep("idle"); return; }
        setStep("suggesting");
        await suggest({ repo_url: repoUrl, branch, source_job_id: result.job_id, model: selectedModel }).catch(() => {});
        setStep("done");
    }

    async function handleApply() {
        if (!suggestJobId) return;
        await apply({ repo_url: repoUrl, branch, source_job_id: suggestJobId, draft: true });
    }

    function handleReset() {
        reset();
        setStep("idle");
        setExpanded(null);
    }

    // ── History ────────────────────────────────────────────────────────────────

    const fetchHistory = useCallback(async () => {
        setHistoryLoading(true);
        try {
            const res = await fetch(`${API_BASE}/agents/refactor/history`, {
                headers: authHeaders(), credentials: "include",
            });
            if (res.ok) {
                const data = await res.json();
                setHistory(data.jobs ?? []);
            }
        } catch { /* ignore */ }
        finally { setHistoryLoading(false); }
    }, []);

    useEffect(() => { if (mainTab === "history") fetchHistory(); }, [mainTab, fetchHistory]);

    return (
        <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-6">

            {/* ── Header ─────────────────────────────────────────────────── */}
            <motion.div variants={itemVariants} className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                        <Code2 className="w-6 h-6 text-emerald-400" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">Code Refactor Agent</h1>
                        <p className="text-muted-foreground text-sm">
                            Standalone analysis or pipeline history — detect smells, generate patches, open PRs
                        </p>
                    </div>
                </div>
                {mainTab === "standalone" && step !== "idle" && (
                    <Button size="sm" onClick={handleReset} className="bg-white/5 text-muted-foreground border border-white/10 hover:bg-white/10 text-xs">
                        <RefreshCw className="w-3 h-3 mr-1" /> New Analysis
                    </Button>
                )}
            </motion.div>

            {/* ── Main Tabs ──────────────────────────────────────────────── */}
            <motion.div variants={itemVariants} className="flex gap-1 bg-white/5 border border-white/8 rounded-xl p-1 w-fit">
                {([
                    { key: "standalone", label: "Standalone Refactor", icon: Cpu     },
                    { key: "history",    label: "Pipeline History",     icon: History },
                ] as { key: MainTab; label: string; icon: React.ElementType }[]).map(t => (
                    <button
                        key={t.key}
                        onClick={() => setMainTab(t.key)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${mainTab === t.key ? "bg-white/10 text-white shadow" : "text-muted-foreground hover:text-white"}`}
                    >
                        <t.icon className="w-4 h-4" />
                        {t.label}
                    </button>
                ))}
            </motion.div>

            {/* ══════════════════ STANDALONE TAB ════════════════════ */}
            {mainTab === "standalone" && (
                <>
                    {/* Agent Status Panel */}
                    <motion.div variants={itemVariants}>
                        <Card className="bg-card border-white/5">
                            <CardHeader className="flex flex-row items-center justify-between pb-3">
                                <CardTitle className="text-white text-sm flex items-center gap-2">
                                    <Activity className="w-4 h-4 text-cyan-400" />
                                    Agent Status
                                </CardTitle>
                                <button onClick={fetchAgents} disabled={agentsLoading} className="text-muted-foreground hover:text-white transition-colors">
                                    <RefreshCw className={`w-3.5 h-3.5 ${agentsLoading ? "animate-spin" : ""}`} />
                                </button>
                            </CardHeader>
                            <CardContent>
                                {agentsLoading ? (
                                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                        <RotateCw className="w-3 h-3 animate-spin" /> Loading agents…
                                    </div>
                                ) : agents.length === 0 ? (
                                    <p className="text-xs text-muted-foreground">No agents found.</p>
                                ) : (
                                    <div className="flex flex-wrap gap-2">
                                        {agents.map((agent, i) => (
                                            <Badge key={agent.name ?? i} className={`${statusColor(agent.status)} text-xs capitalize flex items-center gap-1.5`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${statusDot(agent.status)}`} />
                                                {agent.name}
                                                <span className="opacity-60">·</span>
                                                {agent.status}
                                            </Badge>
                                        ))}
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </motion.div>

                    {/* Step 1 — Analyze Form */}
                    {step === "idle" && (
                        <motion.div variants={itemVariants}>
                            <Card className="bg-card border-white/5">
                                <CardHeader>
                                    <CardTitle className="text-white text-base flex items-center gap-2">
                                        <Cpu className="w-4 h-4 text-emerald-400" />
                                        Phase 1 — Repository Analysis
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div className="md:col-span-2 space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Repository URL *</Label>
                                            <Input
                                                value={repoUrl}
                                                onChange={e => setRepoUrl(e.target.value)}
                                                placeholder="https://github.com/org/repo"
                                                className="bg-white/5 border-white/10 text-white placeholder:text-white/20 text-sm"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Branch</Label>
                                            <Input value={branch} onChange={e => setBranch(e.target.value)} placeholder="master" className="bg-white/5 border-white/10 text-white placeholder:text-white/20 text-sm" />
                                        </div>
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-muted-foreground">Severity Threshold</Label>
                                            <select
                                                value={severityThreshold}
                                                onChange={e => setSeverityThreshold(e.target.value)}
                                                className="w-full h-9 rounded-md px-3 bg-white/5 border border-white/10 text-white text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
                                            >
                                                <option value="low"    className="bg-[#0a0f1a]">Low</option>
                                                <option value="medium" className="bg-[#0a0f1a]">Medium</option>
                                                <option value="high"   className="bg-[#0a0f1a]">High</option>
                                            </select>
                                        </div>

                                        <div className="md:col-span-2 space-y-1.5">
                                            <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                                                <Sparkles className="w-3 h-3 text-violet-400" />
                                                Model
                                                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">free</span>
                                            </Label>
                                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                                                {OPENROUTER_FREE_MODELS.map(m => (
                                                    <button
                                                        key={m.id}
                                                        type="button"
                                                        onClick={() => setSelectedModel(m.id)}
                                                        className={`p-3 rounded-xl border text-left transition-all ${
                                                            selectedModel === m.id
                                                                ? "bg-violet-500/10 border-violet-500/30 shadow-[0_0_12px_rgba(139,92,246,0.1)]"
                                                                : "bg-white/[0.02] border-white/5 hover:border-white/10"
                                                        }`}
                                                    >
                                                        <div className="flex items-start justify-between gap-1">
                                                            <span className="text-xs font-medium text-white leading-tight">{m.label}</span>
                                                            {selectedModel === m.id && <CheckCircle2 className="w-3.5 h-3.5 text-violet-400 shrink-0 mt-0.5" />}
                                                        </div>
                                                        <span className="text-[10px] text-muted-foreground mt-0.5 block">{m.provider}</span>
                                                    </button>
                                                ))}
                                            </div>
                                            <p className="text-[11px] text-muted-foreground font-mono truncate opacity-60">{selectedModel}</p>
                                        </div>
                                    </div>

                                    {error && (
                                        <div className="p-3 rounded-lg bg-rose-500/5 border border-rose-500/20 text-xs text-rose-400">{error}</div>
                                    )}

                                    <Button
                                        onClick={handleAnalyze}
                                        disabled={isRunning || !repoUrl.trim()}
                                        className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 hover:shadow-[0_0_20px_rgba(16,185,129,0.15)] transition-all"
                                    >
                                        <Play className="w-4 h-4 mr-2" />
                                        Start Analysis
                                    </Button>
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}

                    {/* Step 2 — Progress */}
                    {(step === "analyzing" || step === "polling" || step === "suggesting") && (
                        <motion.div variants={itemVariants}>
                            <Card className="bg-card border-white/5">
                                <CardContent className="p-6 space-y-4">
                                    <div className="flex items-center gap-3 flex-wrap">
                                        {[
                                            { label: "Submitting Job",          active: step === "analyzing"  },
                                            { label: "Running Analysis",         active: step === "polling"    },
                                            { label: "Generating Suggestions",   active: step === "suggesting" },
                                        ].map((s, i) => (
                                            <div key={s.label} className="flex items-center gap-2">
                                                <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border transition-all ${s.active ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" : "bg-white/[0.02] border-white/5 text-muted-foreground"}`}>
                                                    {s.active && <RotateCw className="w-3 h-3 animate-spin" />}
                                                    {s.label}
                                                </div>
                                                {i < 2 && <ArrowRight className="w-3 h-3 text-white/10 shrink-0" />}
                                            </div>
                                        ))}
                                    </div>

                                    {jobId && (
                                        <div className="flex items-center gap-4 text-xs text-muted-foreground font-mono">
                                            <span>Job: <span className="text-white/60">{jobId.slice(0, 8)}</span></span>
                                            <span>Model: <span className="text-violet-400">{OPENROUTER_FREE_MODELS.find(m => m.id === selectedModel)?.label ?? selectedModel}</span></span>
                                        </div>
                                    )}

                                    {jobStatus && (
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                            {[
                                                { label: "Status",       value: jobStatus.status },
                                                { label: "Phase",        value: jobStatus.phase ?? "—" },
                                                { label: "Smells Found", value: String(smellCount) },
                                                { label: "Duration",     value: jobStatus.duration_s ? `${jobStatus.duration_s}s` : "—" },
                                            ].map(it => (
                                                <div key={it.label} className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{it.label}</p>
                                                    <p className="text-sm font-semibold text-white mt-1 capitalize">{it.value}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {error && (
                                        <div className="p-3 rounded-lg bg-rose-500/5 border border-rose-500/20 text-xs text-rose-400 flex items-center gap-2">
                                            <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {error}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}

                    {/* Step 3 — Job Result Summary */}
                    {(step === "suggesting" || step === "done") && jobStatus && (
                        <motion.div variants={itemVariants} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                            <Card className="bg-card border-white/5">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle className="text-white text-base flex items-center gap-2">
                                        <Bug className="w-4 h-4 text-rose-400" />
                                        Analysis Results
                                        {jobId && <span className="text-xs font-normal text-muted-foreground font-mono ml-1">#{jobId.slice(0, 8)}</span>}
                                    </CardTitle>
                                    <Badge className={statusColor(jobStatus.status)}>
                                        <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${statusDot(jobStatus.status)}`} />
                                        {jobStatus.status}
                                    </Badge>
                                </CardHeader>
                                <CardContent className="space-y-3">
                                    {jobStatus.changes_summary && (
                                        <div className="grid grid-cols-3 gap-3">
                                            {[
                                                { label: "Files Modified",  value: jobStatus.changes_summary.files_modified,  color: "text-cyan-400"    },
                                                { label: "Smells Detected", value: jobStatus.changes_summary.smells_detected,  color: "text-rose-400"    },
                                                { label: "Smells Fixed",    value: jobStatus.changes_summary.smells_fixed,     color: "text-emerald-400" },
                                            ].map(s => (
                                                <div key={s.label} className="p-4 rounded-xl bg-white/[0.02] border border-white/5">
                                                    <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
                                                    <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {jobStatus.smells && jobStatus.smells.length > 0 && (
                                        <div className="space-y-2">
                                            <p className="text-xs text-muted-foreground uppercase tracking-wider">Detected Smells</p>
                                            {jobStatus.smells.map((smell, i) => (
                                                <div key={i} className="p-3 rounded-lg bg-rose-500/5 border border-rose-500/10 space-y-1">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs font-medium text-white">{smell.smell_type}</span>
                                                        {smell.severity && <Badge className="text-[10px] px-1.5 py-0 bg-rose-500/10 text-rose-400 border-0">{smell.severity}</Badge>}
                                                    </div>
                                                    <p className="text-xs text-muted-foreground">{smell.description}</p>
                                                    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground font-mono">
                                                        <FileCode className="w-3 h-3" />
                                                        {smell.file_path}{smell.line_start && `:${smell.line_start}`}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}

                    {/* Step 4 — Suggestions */}
                    {step === "done" && suggestionList.length > 0 && (
                        <motion.div variants={itemVariants} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                            <Card className="bg-card border-white/5">
                                <CardHeader className="flex flex-row items-center justify-between">
                                    <CardTitle className="text-white text-base flex items-center gap-2">
                                        <Sparkles className="w-4 h-4 text-violet-400" />
                                        Refactor Suggestions
                                        <Badge className="bg-violet-500/10 text-violet-400 border-violet-500/20 text-[10px]">{suggestionList.length}</Badge>
                                    </CardTitle>
                                    {!prUrl && (
                                        <Button size="sm" onClick={handleApply} disabled={applyLoading || !suggestJobId}
                                            className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 text-xs">
                                            {applyLoading ? <RotateCw className="w-3 h-3 mr-1 animate-spin" /> : <GitCompare className="w-3 h-3 mr-1" />}
                                            Apply &amp; Open PR
                                        </Button>
                                    )}
                                    {prUrl && (
                                        <a href={prUrl} target="_blank" rel="noopener noreferrer"
                                            className="flex items-center gap-1.5 text-xs text-emerald-400 hover:underline">
                                            <ExternalLink className="w-3.5 h-3.5" /> View PR
                                        </a>
                                    )}
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    {suggestions?.summary && (
                                        <p className="text-xs text-muted-foreground pb-2 border-b border-white/5">{suggestions.summary}</p>
                                    )}
                                    {suggestionList.map((s, i) => (
                                        <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                                            <button
                                                onClick={() => setExpanded(expandedSuggestion === i ? null : i)}
                                                className="w-full p-4 rounded-xl border bg-violet-500/5 border-violet-500/10 hover:border-violet-500/20 text-left transition-all"
                                            >
                                                <div className="flex items-start justify-between gap-2">
                                                    <div className="flex items-start gap-2 min-w-0">
                                                        {expandedSuggestion === i ? <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" /> : <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />}
                                                        <div className="min-w-0">
                                                            <div className="flex items-center gap-2 flex-wrap">
                                                                <span className="text-sm font-medium text-white">{s.smell_type ?? "Suggestion"}</span>
                                                                {s.severity && (
                                                                    <Badge className={`text-[10px] px-1.5 py-0 border-0 ${s.severity === "high" || s.severity === "critical" ? "bg-rose-500/10 text-rose-400" : s.severity === "medium" ? "bg-amber-500/10 text-amber-400" : "bg-white/5 text-muted-foreground"}`}>
                                                                        {s.severity}
                                                                    </Badge>
                                                                )}
                                                            </div>
                                                            <p className="text-xs text-muted-foreground mt-0.5">{s.description}</p>
                                                            <div className="flex items-center gap-1.5 mt-1 text-[11px] text-muted-foreground font-mono">
                                                                <FileCode className="w-3 h-3" />{s.file_path}{s.line_start && `:${s.line_start}`}
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                                                </div>
                                            </button>

                                            <AnimatePresence>
                                                {expandedSuggestion === i && (
                                                    <motion.div
                                                        initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                                                        transition={{ duration: 0.2 }} className="overflow-hidden"
                                                    >
                                                        <div className="mt-2 ml-6 space-y-2">
                                                            {s.explanation && (
                                                                <p className="text-xs text-muted-foreground p-3 rounded-lg bg-white/[0.02] border border-white/5">{s.explanation}</p>
                                                            )}
                                                            {(s.original_code || s.refactored_code || s.patch) && (
                                                                <Tabs defaultValue={s.patch ? "patch" : "before"} className="w-full">
                                                                    <TabsList className="bg-white/5 border border-white/10">
                                                                        {s.patch && <TabsTrigger value="patch" className="data-[state=active]:bg-cyan-500/10 data-[state=active]:text-cyan-400 text-xs">Unified Diff</TabsTrigger>}
                                                                        {s.original_code && <TabsTrigger value="before" className="data-[state=active]:bg-rose-500/10 data-[state=active]:text-rose-400 text-xs">Before</TabsTrigger>}
                                                                        {s.refactored_code && <TabsTrigger value="after" className="data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-400 text-xs">After</TabsTrigger>}
                                                                    </TabsList>
                                                                    {s.patch && <TabsContent value="patch"><div className="mt-2 bg-[#0a0f1a] rounded-xl p-4 font-mono text-xs border border-cyan-500/10 overflow-x-auto"><pre className="text-cyan-300/80 whitespace-pre">{s.patch}</pre></div></TabsContent>}
                                                                    {s.original_code && <TabsContent value="before"><div className="mt-2 bg-[#0a0f1a] rounded-xl p-4 font-mono text-xs border border-rose-500/10 overflow-x-auto"><pre className="text-rose-300/80 whitespace-pre">{s.original_code}</pre></div></TabsContent>}
                                                                    {s.refactored_code && <TabsContent value="after"><div className="mt-2 bg-[#0a0f1a] rounded-xl p-4 font-mono text-xs border border-emerald-500/10 overflow-x-auto"><pre className="text-emerald-300/80 whitespace-pre">{s.refactored_code}</pre></div></TabsContent>}
                                                                </Tabs>
                                                            )}
                                                        </div>
                                                    </motion.div>
                                                )}
                                            </AnimatePresence>
                                        </motion.div>
                                    ))}
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}

                    {/* Done — error */}
                    {step === "done" && suggestionList.length === 0 && !suggestLoading && error && (
                        <motion.div variants={itemVariants}>
                            <Card className="bg-rose-500/5 border-rose-500/20">
                                <CardContent className="p-6 flex items-start gap-3">
                                    <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
                                    <div className="space-y-1">
                                        <p className="text-sm font-medium text-rose-400">Refactor suggestion failed</p>
                                        <p className="text-xs text-rose-300/70">{error}</p>
                                    </div>
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}

                    {/* Done — no suggestions, no error */}
                    {step === "done" && suggestionList.length === 0 && !suggestLoading && !error && (
                        <motion.div variants={itemVariants}>
                            <Card className="bg-card border-white/5">
                                <CardContent className="p-6 flex items-center gap-3 text-emerald-400">
                                    <CheckCircle2 className="w-5 h-5 shrink-0" />
                                    <p className="text-sm">No refactor suggestions — the LLM reviewed your code and found no issues to fix.</p>
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}

                    {/* PR success banner */}
                    {prUrl && (
                        <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}>
                            <Card className="bg-emerald-500/5 border-emerald-500/20">
                                <CardContent className="p-4 flex items-center justify-between">
                                    <div className="flex items-center gap-2 text-emerald-400">
                                        <CheckCircle2 className="w-4 h-4" />
                                        <span className="text-sm font-medium">Pull Request opened successfully</span>
                                    </div>
                                    <a href={prUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-xs text-emerald-400 hover:underline">
                                        <ExternalLink className="w-3.5 h-3.5" /> View PR
                                    </a>
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}
                </>
            )}

            {/* ══════════════════ HISTORY TAB ════════════════════ */}
            {mainTab === "history" && (
                <motion.div variants={itemVariants}>
                    <Card className="bg-card border-white/5">
                        <CardHeader className="flex flex-row items-center justify-between">
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <History className="w-4 h-4 text-emerald-400" />
                                Refactor Job History
                                <span className="text-xs text-muted-foreground font-normal">(autonomous pipeline + standalone)</span>
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
                                    <p className="text-sm text-muted-foreground">No refactor jobs yet.</p>
                                    <p className="text-xs text-muted-foreground/60">Use Standalone Refactor or the Autonomous Pipeline to create jobs.</p>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {history.map((job, i) => (
                                        <motion.div
                                            key={job.job_id}
                                            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                                            className="flex items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-all"
                                        >
                                            <div className={`w-2 h-2 rounded-full shrink-0 ${statusDot(job.status)}`} />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <p className="text-sm text-white font-mono">{job.job_id.slice(0, 16)}</p>
                                                    <Badge className={`text-[10px] border-0 ${statusColor(job.status)}`}>{job.status}</Badge>
                                                    <Badge className="text-[10px] bg-white/5 text-muted-foreground border-0 capitalize">{job.phase}</Badge>
                                                </div>
                                                {job.error && <p className="text-[11px] text-rose-400 mt-0.5 truncate">{job.error}</p>}
                                            </div>
                                            <div className="text-right shrink-0 space-y-0.5">
                                                {job.duration_s !== undefined && (
                                                    <p className="text-xs text-emerald-400 flex items-center gap-1 justify-end">
                                                        <Clock className="w-3 h-3" /> {job.duration_s.toFixed(1)}s
                                                    </p>
                                                )}
                                                <p className="text-[10px] text-muted-foreground">
                                                    {job.created_at ? relTime(job.created_at) : "—"}
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
