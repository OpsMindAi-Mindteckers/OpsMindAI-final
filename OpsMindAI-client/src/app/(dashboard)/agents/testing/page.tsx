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
    FileCheck,
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
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTesting } from "@/lib/hooks/use-testing";
import { testingService } from "@/lib/services/testing-service";
import type { TestingJobStatus } from "@/lib/api-types";

// ── Free models list (same set as code-refactor) ─────────────────────────────
const OPENROUTER_FREE_MODELS = [
     { id: "openrouter/free",                          label: "Free Router",            provider: "OpenRouter" },
    { id: "openai/gpt-oss-120b:free",                  label: "GPT OSS 120B",          provider: "OpenAI" },
    { id: "openai/gpt-oss-20b:free",                   label: "GPT OSS 20B",            provider: "OpenAI" },
    { id: "qwen/qwen3-coder:free",                     label: "Qwen3 Coder",            provider: "Qwen" },
    { id: "deepseek/deepseek-v4-flash:free",           label: "DeepSeek V4 Flash",      provider: "DeepSeek" },
    { id: "meta-llama/llama-3.3-70b-instruct:free",    label: "Llama 3.3 70B",          provider: "Meta" },
    { id: "nvidia/nemotron-3-super-120b-a12b:free",    label: "Nemotron Super 120B",    provider: "NVIDIA" },
    { id: "google/gemma-4-31b-it:free",                label: "Gemma 4 31B",            provider: "Google" },
    { id: "nousresearch/hermes-3-llama-3.1-405b:free", label: "Hermes 3 405B",          provider: "NousResearch" },
    { id: "minimax/minimax-m2.5:free",                 label: "MiniMax M2.5",           provider: "MiniMax" },
    { id: "openrouter/free",                          label: "Free Router",            provider: "OpenRouter" },
    { id: "arcee-ai/trinity-large-thinking:free",      label: "Trinity Thinking",       provider: "Arcee AI" },
];

// ── Animation variants ────────────────────────────────────────────────────────
const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};
const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
};

// ── Status helpers ────────────────────────────────────────────────────────────
function statusColor(status: string) {
    switch (status?.toLowerCase()) {
        case "completed":
        case "generation_complete": return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
        case "running": return "bg-cyan-500/10 text-cyan-400 border-cyan-500/20";
        case "queued":
        case "pending": return "bg-amber-500/10 text-amber-400 border-amber-500/20";
        case "failed":
        case "error": return "bg-rose-500/10 text-rose-400 border-rose-500/20";
        default: return "bg-white/5 text-muted-foreground border-white/10";
    }
}
function statusDot(status: string) {
    switch (status?.toLowerCase()) {
        case "completed":
        case "generation_complete": return "bg-emerald-400";
        case "running": return "bg-cyan-400 animate-pulse";
        case "queued":
        case "pending": return "bg-amber-400 animate-pulse";
        case "failed": return "bg-rose-400";
        default: return "bg-white/20";
    }
}
function isTerminal(status: string) {
    return ["completed", "failed", "error", "generation_complete"].includes(status?.toLowerCase());
}

// ── Phase label ───────────────────────────────────────────────────────────────
function phaseLabel(phase?: string) {
    switch (phase) {
        case "generation": return "Phase 1 — Generating Tests";
        case "suite_execution": return "Phase 2 — Running Suite";
        case "regression": return "Phase 3 — Regression Suite";
        default: return phase ?? "—";
    }
}

export default function TestingAgentPage() {
    const { generateTests, runTestSuite, buildRegressionSuite, isLoading, error } = useTesting();

    // ── Phase 1 form state ────────────────────────────────────────────────────
    const [repoUrl, setRepoUrl] = useState("");
    const [filePath, setFilePath] = useState("");
    const [branch, setBranch] = useState("main");
    const [framework, setFramework] = useState<"pytest" | "jest">("pytest");
    const [threshold, setThreshold] = useState(0.8);
    const [prNumber, setPrNumber] = useState("");
    const [selectedModel, setSelectedModel] = useState(OPENROUTER_FREE_MODELS[0].id);

    // ── Phase 3 regression form ───────────────────────────────────────────────
    const [regRepoUrl, setRegRepoUrl] = useState("");
    const [regBranch, setRegBranch] = useState("main");
    const [triggerType, setTriggerType] = useState("incident");
    const [incidentId, setIncidentId] = useState("");

    // ── Job tracking state ────────────────────────────────────────────────────
    const [genJobId, setGenJobId] = useState<string | null>(null);
    const [genJobStatus, setGenJobStatus] = useState<TestingJobStatus | null>(null);
    const [suiteJobId, setSuiteJobId] = useState<string | null>(null);
    const [suiteJobStatus, setSuiteJobStatus] = useState<TestingJobStatus | null>(null);
    const [regJobId, setRegJobId] = useState<string | null>(null);
    const [regJobStatus, setRegJobStatus] = useState<TestingJobStatus | null>(null);

    const [expandedFile, setExpandedFile] = useState<string | null>(null);
    const [agentStatus, setAgentStatus] = useState<string>("idle");
    const [agentStatusLoading, setAgentStatusLoading] = useState(false);

    // ── Polling refs ──────────────────────────────────────────────────────────
    const genPollRef = useRef<NodeJS.Timeout | null>(null);
    const suitePollRef = useRef<NodeJS.Timeout | null>(null);
    const regPollRef = useRef<NodeJS.Timeout | null>(null);

    const pollJob = useCallback(async (
        jobId: string,
        setter: (s: TestingJobStatus) => void,
        ref: React.MutableRefObject<NodeJS.Timeout | null>
    ) => {
        const status = await testingService.getJobStatus(jobId);
        if (status) {
            setter(status);
            if (isTerminal(status.status)) {
                if (ref.current) clearInterval(ref.current);
                ref.current = null;
                setAgentStatus("idle");
            }
        }
    }, []);

    // Auto-poll generation job
    useEffect(() => {
        if (!genJobId) return;
        genPollRef.current = setInterval(() => pollJob(genJobId, setGenJobStatus, genPollRef), 2000);
        return () => { if (genPollRef.current) clearInterval(genPollRef.current); };
    }, [genJobId, pollJob]);

    // Auto-poll suite job
    useEffect(() => {
        if (!suiteJobId) return;
        suitePollRef.current = setInterval(() => pollJob(suiteJobId, setSuiteJobStatus, suitePollRef), 2000);
        return () => { if (suitePollRef.current) clearInterval(suitePollRef.current); };
    }, [suiteJobId, pollJob]);

    // Auto-poll regression job
    useEffect(() => {
        if (!regJobId) return;
        regPollRef.current = setInterval(() => pollJob(regJobId, setRegJobStatus, regPollRef), 2000);
        return () => { if (regPollRef.current) clearInterval(regPollRef.current); };
    }, [regJobId, pollJob]);

    // ── Phase 1: Generate ─────────────────────────────────────────────────────
    async function handleGenerate() {
        if (!repoUrl.trim()) return;
        setAgentStatus("running");
        setGenJobStatus(null);
        setSuiteJobStatus(null);
        const result = await generateTests({
            repo_url: repoUrl.trim(),
            file_path: filePath.trim() || undefined,
            branch: branch.trim() || "main",
            framework,
            coverage_threshold: threshold,
            pr_number: prNumber ? parseInt(prNumber) : undefined,
            model: selectedModel,
        });
        if (result?.job_id) {
            setGenJobId(result.job_id);
            setGenJobStatus({ job_id: result.job_id, status: "queued", phase: "generation" });
        } else {
            setAgentStatus("idle");
        }
    }

    // ── Phase 2: Run Suite ────────────────────────────────────────────────────
    async function handleRunSuite() {
        if (!genJobId) return;
        setAgentStatus("running");
        setSuiteJobStatus(null);
        const result = await runTestSuite({
            generation_job_id: genJobId,
            pr_number: prNumber ? parseInt(prNumber) : undefined,
        });
        if (result?.job_id) {
            setSuiteJobId(result.job_id);
            setSuiteJobStatus({ job_id: result.job_id, status: "queued", phase: "suite_execution" });
        } else {
            setAgentStatus("idle");
        }
    }

    // ── Phase 3: Regression ───────────────────────────────────────────────────
    async function handleRegression() {
        if (!regRepoUrl.trim()) return;
        setAgentStatus("running");
        setRegJobStatus(null);
        const result = await buildRegressionSuite({
            repo_url: regRepoUrl.trim(),
            branch: regBranch.trim() || "main",
            trigger_event: {
                type: triggerType,
                ...(incidentId ? { incident_id: incidentId } : {}),
            },
        });
        if (result?.job_id) {
            setRegJobId(result.job_id);
            setRegJobStatus({ job_id: result.job_id, status: "queued", phase: "regression" });
        } else {
            setAgentStatus("idle");
        }
    }

    function handleReset() {
        if (genPollRef.current) clearInterval(genPollRef.current);
        if (suitePollRef.current) clearInterval(suitePollRef.current);
        setGenJobId(null); setGenJobStatus(null);
        setSuiteJobId(null); setSuiteJobStatus(null);
        setAgentStatus("idle");
    }

    const genComplete = genJobStatus?.status === "generation_complete" || genJobStatus?.status === "completed";
    const coveragePct = suiteJobStatus?.coverage?.coverage_pct ?? 0;
    const gatePassed = suiteJobStatus?.gate_passed;

    return (
        <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="space-y-6"
        >
            {/* ── Header ──────────────────────────────────────────────────── */}
            <motion.div variants={itemVariants} className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                        <TestTube2 className="w-6 h-6 text-violet-400" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">Testing Agent</h1>
                        <p className="text-muted-foreground text-sm">
                            Generate test stubs, enforce coverage gates & build regression suites
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium ${statusColor(agentStatus)}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${statusDot(agentStatus)}`} />
                        {agentStatus.charAt(0).toUpperCase() + agentStatus.slice(1)}
                    </div>
                </div>
            </motion.div>

            {/* ── Error banner ─────────────────────────────────────────────── */}
            <AnimatePresence>
                {error && (
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="flex items-center gap-3 px-4 py-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm"
                    >
                        <AlertTriangle className="w-4 h-4 shrink-0" />
                        <span>{error}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* ── Main Tabs ─────────────────────────────────────────────────── */}
            <motion.div variants={itemVariants}>
                <Tabs defaultValue="generate">
                    <TabsList className="bg-white/5 border border-white/10 mb-6">
                        <TabsTrigger value="generate" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-300">
                            <FlaskConical className="w-4 h-4 mr-2" /> Phase 1 — Generate
                        </TabsTrigger>
                        <TabsTrigger value="suite" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-300">
                            <Shield className="w-4 h-4 mr-2" /> Phase 2 — Suite
                        </TabsTrigger>
                        <TabsTrigger value="regression" className="data-[state=active]:bg-violet-500/20 data-[state=active]:text-violet-300">
                            <Bug className="w-4 h-4 mr-2" /> Phase 3 — Regression
                        </TabsTrigger>
                    </TabsList>

                    {/* ══════════════════ PHASE 1 — GENERATE ══════════════════ */}
                    <TabsContent value="generate" className="space-y-4">
                        <Card className="bg-card border-white/5">
                            <CardHeader className="pb-4">
                                <CardTitle className="text-white text-sm flex items-center gap-2">
                                    <FlaskConical className="w-4 h-4 text-violet-400" />
                                    Phase 1 — Repository Analysis &amp; Test Generation
                                </CardTitle>
                                <p className="text-xs text-muted-foreground mt-1">
                                    Clone the repository, analyse source files with the LLM, and write test stubs.
                                    Leave <code className="bg-white/10 px-1 rounded text-violet-300">File Path</code> empty
                                    to scan the entire repo.
                                </p>
                            </CardHeader>
                            <CardContent className="space-y-5">
                                {/* Repo URL */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">Repository URL *</Label>
                                    <Input
                                        placeholder="https://github.com/org/repo"
                                        value={repoUrl}
                                        onChange={(e) => setRepoUrl(e.target.value)}
                                        className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground/50 h-9 text-sm"
                                    />
                                </div>

                                {/* Row: Branch + File Path */}
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">Branch</Label>
                                        <Input
                                            placeholder="main"
                                            value={branch}
                                            onChange={(e) => setBranch(e.target.value)}
                                            className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground/50 h-9 text-sm"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">File Path (optional)</Label>
                                        <Input
                                            placeholder="src/services/auth.py"
                                            value={filePath}
                                            onChange={(e) => setFilePath(e.target.value)}
                                            className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground/50 h-9 text-sm"
                                        />
                                    </div>
                                </div>

                                {/* Row: Framework + Threshold + PR */}
                                <div className="grid grid-cols-3 gap-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">Framework</Label>
                                        <div className="flex gap-2">
                                            {(["pytest", "jest"] as const).map((fw) => (
                                                <button
                                                    key={fw}
                                                    onClick={() => setFramework(fw)}
                                                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium border transition-all ${framework === fw
                                                        ? "bg-violet-500/20 border-violet-500/40 text-violet-300"
                                                        : "bg-white/5 border-white/10 text-muted-foreground hover:border-white/20"
                                                        }`}
                                                >
                                                    {fw}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">
                                            Coverage Gate: <span className="text-violet-400">{Math.round(threshold * 100)}%</span>
                                        </Label>
                                        <input
                                            type="range" min={0} max={1} step={0.05}
                                            value={threshold}
                                            onChange={(e) => setThreshold(parseFloat(e.target.value))}
                                            className="w-full accent-violet-500 mt-2"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">PR Number (optional)</Label>
                                        <Input
                                            placeholder="42"
                                            value={prNumber}
                                            onChange={(e) => setPrNumber(e.target.value)}
                                            className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground/50 h-9 text-sm"
                                        />
                                    </div>
                                </div>

                                {/* Model selector */}
                                <div className="space-y-2">
                                    <Label className="text-xs text-muted-foreground flex items-center gap-1.5">
                                        <Cpu className="w-3 h-3" /> Model
                                        <span className="bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 text-[10px] px-1.5 py-0.5 rounded-full font-medium">free</span>
                                    </Label>
                                    <div className="grid grid-cols-3 gap-2">
                                        {OPENROUTER_FREE_MODELS.map((m) => (
                                            <button
                                                key={m.id}
                                                onClick={() => setSelectedModel(m.id)}
                                                className={`p-2.5 rounded-xl border text-left transition-all ${selectedModel === m.id
                                                    ? "bg-violet-500/15 border-violet-500/40"
                                                    : "bg-white/[0.03] border-white/10 hover:border-white/20"
                                                    }`}
                                            >
                                                <p className="text-xs font-medium text-white leading-tight">{m.label}</p>
                                                <p className="text-[10px] text-muted-foreground mt-0.5">{m.provider}</p>
                                                {selectedModel === m.id && (
                                                    <p className="text-[10px] text-violet-400 mt-0.5 truncate">{m.id}</p>
                                                )}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Submit */}
                                <div className="flex items-center gap-3 pt-1">
                                    <Button
                                        onClick={handleGenerate}
                                        disabled={!repoUrl.trim() || isLoading || agentStatus === "running"}
                                        className="bg-violet-500/15 text-violet-300 border border-violet-500/30 hover:bg-violet-500/25 hover:shadow-[0_0_20px_rgba(139,92,246,0.2)] transition-all disabled:opacity-40"
                                    >
                                        {isLoading ? (
                                            <RotateCw className="w-4 h-4 mr-2 animate-spin" />
                                        ) : (
                                            <Play className="w-4 h-4 mr-2" />
                                        )}
                                        Generate Tests
                                    </Button>
                                    {(genJobId || suiteJobId) && (
                                        <button onClick={handleReset} className="text-xs text-muted-foreground hover:text-white transition-colors">
                                            Reset
                                        </button>
                                    )}
                                </div>
                            </CardContent>
                        </Card>

                        {/* ── Generation job status ─────────────────────────── */}
                        <AnimatePresence>
                            {genJobStatus && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0 }}
                                >
                                    <Card className="bg-card border-white/5">
                                        <CardHeader className="pb-3 flex flex-row items-center justify-between">
                                            <CardTitle className="text-white text-sm flex items-center gap-2">
                                                <Activity className="w-4 h-4 text-violet-400" />
                                                Generation Job
                                                <code className="text-[10px] bg-white/10 px-1.5 py-0.5 rounded text-muted-foreground">{genJobId}</code>
                                            </CardTitle>
                                            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs ${statusColor(genJobStatus.status)}`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${statusDot(genJobStatus.status)}`} />
                                                {genJobStatus.status}
                                            </div>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                            {/* Phase + duration */}
                                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                                                <span className="flex items-center gap-1.5">
                                                    <Terminal className="w-3 h-3" />
                                                    {phaseLabel(genJobStatus.phase)}
                                                </span>
                                                {genJobStatus.duration_s && (
                                                    <span className="flex items-center gap-1">
                                                        <Clock className="w-3 h-3" /> {genJobStatus.duration_s.toFixed(1)}s
                                                    </span>
                                                )}
                                            </div>

                                            {/* Running spinner */}
                                            {!isTerminal(genJobStatus.status) && (
                                                <div className="flex items-center gap-2 text-xs text-cyan-400">
                                                    <RotateCw className="w-3 h-3 animate-spin" />
                                                    Polling for updates...
                                                </div>
                                            )}

                                            {/* Error */}
                                            {genJobStatus.error && (
                                                <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                                                    <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
                                                    <span>{genJobStatus.error}</span>
                                                </div>
                                            )}

                                            {/* Generated files */}
                                            {genComplete && genJobStatus.generated_files && genJobStatus.generated_files.length > 0 && (
                                                <div className="space-y-2">
                                                    <p className="text-xs font-medium text-white flex items-center gap-1.5">
                                                        <FileCheck className="w-3.5 h-3.5 text-emerald-400" />
                                                        {genJobStatus.generated_files.length} file(s) generated
                                                    </p>
                                                    {genJobStatus.generated_files.map((f) => (
                                                        <button
                                                            key={f.source_file}
                                                            onClick={() => setExpandedFile(expandedFile === f.source_file ? null : f.source_file)}
                                                            className="w-full p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/15 text-left hover:border-emerald-500/25 transition-all"
                                                        >
                                                            <div className="flex items-center justify-between">
                                                                <div className="flex items-center gap-2">
                                                                    {expandedFile === f.source_file
                                                                        ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                                                                        : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
                                                                    <FileText className="w-3.5 h-3.5 text-violet-400" />
                                                                    <span className="text-xs text-white font-mono">{f.source_file}</span>
                                                                </div>
                                                                <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                                                                    <span>{f.functions_processed} fn</span>
                                                                    <span>{f.tokens_used} tok</span>
                                                                </div>
                                                            </div>
                                                            {expandedFile === f.source_file && (
                                                                <div className="mt-2 ml-6 space-y-1 text-[10px] text-muted-foreground">
                                                                    <p>Output: <span className="text-violet-300 font-mono">{f.output_file}</span></p>
                                                                    <p>Model: <span className="text-cyan-300">{f.model_used}</span></p>
                                                                </div>
                                                            )}
                                                        </button>
                                                    ))}
                                                </div>
                                            )}

                                            {/* Warnings */}
                                            {genJobStatus.warnings && genJobStatus.warnings.length > 0 && (
                                                <div className="space-y-1">
                                                    {genJobStatus.warnings.map((w, i) => (
                                                        <div key={i} className="flex items-start gap-2 text-xs text-amber-400">
                                                            <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
                                                            <span>{w}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}

                                            {/* CTA: run suite */}
                                            {genComplete && (
                                                <div className="flex items-center gap-3 pt-2 border-t border-white/5">
                                                    <div className="flex items-center gap-1.5 text-xs text-emerald-400">
                                                        <CheckCircle2 className="w-3.5 h-3.5" />
                                                        Generation complete — run the suite to enforce coverage gate
                                                    </div>
                                                    <ArrowRight className="w-3.5 h-3.5 text-muted-foreground ml-auto" />
                                                </div>
                                            )}
                                        </CardContent>
                                    </Card>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </TabsContent>

                    {/* ══════════════════ PHASE 2 — SUITE ═════════════════════ */}
                    <TabsContent value="suite" className="space-y-4">
                        <Card className="bg-card border-white/5">
                            <CardHeader className="pb-4">
                                <CardTitle className="text-white text-sm flex items-center gap-2">
                                    <Shield className="w-4 h-4 text-cyan-400" />
                                    Phase 2 — Run Test Suite &amp; Enforce Coverage Gate
                                </CardTitle>
                                <p className="text-xs text-muted-foreground mt-1">
                                    Execute the generated tests against the cloned repo, parse coverage, and enforce the gate.
                                    Requires a completed Phase 1 job.
                                </p>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {/* Generation job ID display */}
                                <div className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.03] border border-white/10">
                                    <Terminal className="w-4 h-4 text-violet-400 shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs text-muted-foreground">Generation Job ID</p>
                                        {genJobId ? (
                                            <p className="text-sm font-mono text-white truncate">{genJobId}</p>
                                        ) : (
                                            <p className="text-xs text-amber-400">
                                                No generation job yet — run Phase 1 first
                                            </p>
                                        )}
                                    </div>
                                    {genComplete && (
                                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                                    )}
                                </div>

                                <Button
                                    onClick={handleRunSuite}
                                    disabled={!genComplete || isLoading || agentStatus === "running"}
                                    className="w-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25 transition-all disabled:opacity-40"
                                >
                                    {isLoading ? (
                                        <RotateCw className="w-4 h-4 mr-2 animate-spin" />
                                    ) : (
                                        <Play className="w-4 h-4 mr-2" />
                                    )}
                                    Run Test Suite
                                </Button>
                            </CardContent>
                        </Card>

                        {/* ── Suite job result ──────────────────────────────── */}
                        <AnimatePresence>
                            {suiteJobStatus && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0 }}
                                    className="space-y-4"
                                >
                                    {/* Status card */}
                                    <Card className="bg-card border-white/5">
                                        <CardHeader className="pb-3 flex flex-row items-center justify-between">
                                            <CardTitle className="text-white text-sm flex items-center gap-2">
                                                <Activity className="w-4 h-4 text-cyan-400" />
                                                Suite Job
                                                <code className="text-[10px] bg-white/10 px-1.5 py-0.5 rounded text-muted-foreground">{suiteJobId}</code>
                                            </CardTitle>
                                            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs ${statusColor(suiteJobStatus.status)}`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${statusDot(suiteJobStatus.status)}`} />
                                                {suiteJobStatus.status}
                                            </div>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                            {!isTerminal(suiteJobStatus.status) && (
                                                <div className="flex items-center gap-2 text-xs text-cyan-400">
                                                    <RotateCw className="w-3 h-3 animate-spin" />
                                                    Executing tests, parsing coverage...
                                                </div>
                                            )}
                                            {suiteJobStatus.error && (
                                                <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                                                    <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
                                                    <span>{suiteJobStatus.error}</span>
                                                </div>
                                            )}
                                        </CardContent>
                                    </Card>

                                    {/* Coverage card */}
                                    {suiteJobStatus.coverage && (
                                        <Card className={`border ${gatePassed ? "bg-emerald-500/5 border-emerald-500/20" : "bg-rose-500/5 border-rose-500/20"}`}>
                                            <CardHeader className="pb-3">
                                                <CardTitle className={`text-sm flex items-center gap-2 ${gatePassed ? "text-emerald-400" : "text-rose-400"}`}>
                                                    {gatePassed
                                                        ? <><CheckCircle2 className="w-4 h-4" /> Coverage Gate Passed</>
                                                        : <><XCircle className="w-4 h-4" /> Coverage Gate Failed</>
                                                    }
                                                </CardTitle>
                                            </CardHeader>
                                            <CardContent className="space-y-4">
                                                {/* Big coverage number */}
                                                <div className="flex items-end gap-3">
                                                    <span className={`text-5xl font-bold ${gatePassed ? "text-emerald-400" : "text-rose-400"}`}>
                                                        {coveragePct.toFixed(1)}%
                                                    </span>
                                                    <div className="pb-1 text-xs text-muted-foreground space-y-0.5">
                                                        <p>threshold: <span className="text-white">{(suiteJobStatus.coverage.threshold * 100).toFixed(0)}%</span></p>
                                                        {suiteJobStatus.coverage.previous_pct !== undefined && (
                                                            <p className="flex items-center gap-1">
                                                                <TrendingUp className="w-3 h-3" />
                                                                prev: {suiteJobStatus.coverage.previous_pct.toFixed(1)}%
                                                                <span className={suiteJobStatus.coverage.delta_pct >= 0 ? "text-emerald-400" : "text-rose-400"}>
                                                                    ({suiteJobStatus.coverage.delta_pct >= 0 ? "+" : ""}{suiteJobStatus.coverage.delta_pct.toFixed(1)}%)
                                                                </span>
                                                            </p>
                                                        )}
                                                    </div>
                                                </div>

                                                {/* Progress bar */}
                                                <div className="relative">
                                                    <Progress
                                                        value={coveragePct}
                                                        className={`h-3 ${gatePassed
                                                            ? "[&>div]:bg-gradient-to-r [&>div]:from-emerald-500 [&>div]:to-cyan-500"
                                                            : "[&>div]:bg-gradient-to-r [&>div]:from-rose-500 [&>div]:to-orange-500"
                                                            }`}
                                                    />
                                                    {/* Threshold marker */}
                                                    <div
                                                        className="absolute top-0 bottom-0 w-0.5 bg-white/40"
                                                        style={{ left: `${suiteJobStatus.coverage.threshold * 100}%` }}
                                                    />
                                                </div>

                                                {/* Lines stats */}
                                                <div className="grid grid-cols-2 gap-3">
                                                    <div className="p-3 rounded-xl bg-white/5 border border-white/10">
                                                        <p className="text-xs text-muted-foreground">Lines Covered</p>
                                                        <p className="text-xl font-bold text-emerald-400 mt-1">
                                                            {suiteJobStatus.coverage.lines_covered.toLocaleString()}
                                                        </p>
                                                    </div>
                                                    <div className="p-3 rounded-xl bg-white/5 border border-white/10">
                                                        <p className="text-xs text-muted-foreground">Total Lines</p>
                                                        <p className="text-xl font-bold text-white mt-1">
                                                            {suiteJobStatus.coverage.lines_total.toLocaleString()}
                                                        </p>
                                                    </div>
                                                </div>

                                                {/* Duration */}
                                                {suiteJobStatus.duration_s && (
                                                    <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                                                        <Clock className="w-3 h-3" /> Completed in {suiteJobStatus.duration_s.toFixed(1)}s
                                                    </p>
                                                )}
                                            </CardContent>
                                        </Card>
                                    )}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </TabsContent>

                    {/* ══════════════════ PHASE 3 — REGRESSION ════════════════ */}
                    <TabsContent value="regression" className="space-y-4">
                        <Card className="bg-card border-white/5">
                            <CardHeader className="pb-4">
                                <CardTitle className="text-white text-sm flex items-center gap-2">
                                    <Bug className="w-4 h-4 text-amber-400" />
                                    Phase 3 — Build Regression Suite
                                </CardTitle>
                                <p className="text-xs text-muted-foreground mt-1">
                                    Generate incident-driven regression tests, load/stress scenarios, and DB perf assertions.
                                    Independent of Phase 1 — provide a repo URL directly.
                                </p>
                            </CardHeader>
                            <CardContent className="space-y-5">
                                {/* Info cards */}
                                <div className="grid grid-cols-3 gap-3">
                                    {[
                                        { icon: Shield, label: "Incident Tests", desc: "Prevent recurrence of past incidents", color: "text-rose-400" },
                                        { icon: Zap, label: "Load Tests", desc: "Stress scenarios for affected endpoints", color: "text-amber-400" },
                                        { icon: BarChart3, label: "DB Perf Tests", desc: "Database performance assertions", color: "text-cyan-400" },
                                    ].map((item) => (
                                        <div key={item.label} className="p-3 rounded-xl bg-white/[0.03] border border-white/10">
                                            <item.icon className={`w-4 h-4 ${item.color} mb-2`} />
                                            <p className="text-xs font-medium text-white">{item.label}</p>
                                            <p className="text-[10px] text-muted-foreground mt-0.5">{item.desc}</p>
                                        </div>
                                    ))}
                                </div>

                                {/* Repo URL */}
                                <div className="space-y-1.5">
                                    <Label className="text-xs text-muted-foreground">Repository URL *</Label>
                                    <Input
                                        placeholder="https://github.com/org/repo"
                                        value={regRepoUrl}
                                        onChange={(e) => setRegRepoUrl(e.target.value)}
                                        className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground/50 h-9 text-sm"
                                    />
                                </div>

                                {/* Branch + Trigger Type */}
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">Branch</Label>
                                        <Input
                                            placeholder="main"
                                            value={regBranch}
                                            onChange={(e) => setRegBranch(e.target.value)}
                                            className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground/50 h-9 text-sm"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">Trigger Type</Label>
                                        <div className="flex gap-2">
                                            {["incident", "deploy", "manual"].map((t) => (
                                                <button
                                                    key={t}
                                                    onClick={() => setTriggerType(t)}
                                                    className={`flex-1 py-1.5 rounded-lg text-xs font-medium border transition-all ${triggerType === t
                                                        ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
                                                        : "bg-white/5 border-white/10 text-muted-foreground hover:border-white/20"
                                                        }`}
                                                >
                                                    {t}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                </div>

                                {/* Incident ID */}
                                {triggerType === "incident" && (
                                    <div className="space-y-1.5">
                                        <Label className="text-xs text-muted-foreground">Incident ID (optional)</Label>
                                        <Input
                                            placeholder="inc_abc123"
                                            value={incidentId}
                                            onChange={(e) => setIncidentId(e.target.value)}
                                            className="bg-white/5 border-white/10 text-white placeholder:text-muted-foreground/50 h-9 text-sm"
                                        />
                                    </div>
                                )}

                                <Button
                                    onClick={handleRegression}
                                    disabled={!regRepoUrl.trim() || isLoading || agentStatus === "running"}
                                    className="w-full bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 transition-all disabled:opacity-40"
                                >
                                    {isLoading ? (
                                        <RotateCw className="w-4 h-4 mr-2 animate-spin" />
                                    ) : (
                                        <Play className="w-4 h-4 mr-2" />
                                    )}
                                    Build Regression Suite
                                </Button>
                            </CardContent>
                        </Card>

                        {/* ── Regression result card ────────────────────────── */}
                        <AnimatePresence>
                            {regJobStatus && (
                                <motion.div
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0 }}
                                >
                                    <Card className="bg-card border-white/5">
                                        <CardHeader className="pb-3 flex flex-row items-center justify-between">
                                            <CardTitle className="text-white text-sm flex items-center gap-2">
                                                <Activity className="w-4 h-4 text-amber-400" />
                                                Regression Job
                                                <code className="text-[10px] bg-white/10 px-1.5 py-0.5 rounded text-muted-foreground">{regJobId}</code>
                                            </CardTitle>
                                            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs ${statusColor(regJobStatus.status)}`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${statusDot(regJobStatus.status)}`} />
                                                {regJobStatus.status}
                                            </div>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                            {!isTerminal(regJobStatus.status) && (
                                                <div className="flex items-center gap-2 text-xs text-amber-400">
                                                    <RotateCw className="w-3 h-3 animate-spin" />
                                                    Generating regression suite...
                                                </div>
                                            )}
                                            {regJobStatus.error && (
                                                <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
                                                    <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
                                                    <span>{regJobStatus.error}</span>
                                                </div>
                                            )}
                                            {regJobStatus.status === "completed" && (
                                                <div className="grid grid-cols-3 gap-3">
                                                    {[
                                                        { label: "Incident Tests", value: regJobStatus.incident_tests_count ?? 0, color: "text-rose-400" },
                                                        { label: "Load Tests", value: regJobStatus.load_tests_count ?? 0, color: "text-amber-400" },
                                                        { label: "DB Perf Tests", value: regJobStatus.db_perf_tests_count ?? 0, color: "text-cyan-400" },
                                                    ].map((stat) => (
                                                        <div key={stat.label} className="p-3 rounded-xl bg-white/5 border border-white/10 text-center">
                                                            <p className={`text-2xl font-bold ${stat.color}`}>{stat.value}</p>
                                                            <p className="text-[10px] text-muted-foreground mt-1">{stat.label}</p>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                            {regJobStatus.output_file && (
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <FileText className="w-3.5 h-3.5 text-violet-400" />
                                                    Output: <span className="text-violet-300 font-mono">{regJobStatus.output_file}</span>
                                                </div>
                                            )}
                                            {regJobStatus.model_used && (
                                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                    <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                                                    Model: <span className="text-cyan-300">{regJobStatus.model_used}</span>
                                                    {regJobStatus.tokens_used && (
                                                        <span>· {regJobStatus.tokens_used.toLocaleString()} tokens</span>
                                                    )}
                                                </div>
                                            )}
                                            {regJobStatus.duration_s && (
                                                <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                                                    <Clock className="w-3 h-3" /> Completed in {regJobStatus.duration_s.toFixed(1)}s
                                                </p>
                                            )}
                                        </CardContent>
                                    </Card>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </TabsContent>
                </Tabs>
            </motion.div>

            {/* ── How it works ─────────────────────────────────────────────── */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-white text-sm flex items-center gap-2">
                            <Info className="w-4 h-4 text-violet-400" />
                            How It Works
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-3 gap-4">
                            {[
                                {
                                    phase: "Phase 1", icon: FlaskConical, color: "text-violet-400 bg-violet-500/10 border-violet-500/20",
                                    title: "Generate Tests",
                                    steps: ["Clone repo & scan files", "Extract function signatures via AST", "LLM generates test stubs", "Write to tests/ directory"],
                                },
                                {
                                    phase: "Phase 2", icon: Shield, color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
                                    title: "Run Suite",
                                    steps: ["Execute pytest/jest", "Parse coverage XML/JSON", "Enforce coverage gate", "Post PR comment on failure"],
                                },
                                {
                                    phase: "Phase 3", icon: Bug, color: "text-amber-400 bg-amber-500/10 border-amber-500/20",
                                    title: "Regression Suite",
                                    steps: ["Load incident history from RAG", "Generate anti-regression tests", "Build load/stress scenarios", "Add DB performance assertions"],
                                },
                            ].map((item) => (
                                <div key={item.phase} className="space-y-3">
                                    <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border ${item.color}`}>
                                        <item.icon className="w-4 h-4" />
                                        <div>
                                            <p className="text-xs font-semibold">{item.phase}</p>
                                            <p className="text-[10px] opacity-80">{item.title}</p>
                                        </div>
                                    </div>
                                    <ul className="space-y-1.5">
                                        {item.steps.map((s, i) => (
                                            <li key={i} className="flex items-center gap-2 text-[11px] text-muted-foreground">
                                                <span className="w-4 h-4 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-[9px] text-white/60 shrink-0">
                                                    {i + 1}
                                                </span>
                                                {s}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </motion.div>
    );
}
