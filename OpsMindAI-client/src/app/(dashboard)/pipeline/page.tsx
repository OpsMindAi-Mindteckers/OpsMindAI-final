"use client";

import { motion } from "framer-motion";
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
    ArrowRight,
    Zap,
    Eye,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";

const pipelineStages = [
    {
        id: "deploy",
        label: "Deploy",
        icon: Rocket,
        status: "completed",
        color: "emerald",
        description: "Application deployed to production cluster",
        details: {
            version: "v2.4.1",
            replicas: "3/3 healthy",
            duration: "2m 34s",
            timestamp: "11:30 AM",
        },
    },
    {
        id: "monitor",
        label: "Monitor",
        icon: Activity,
        status: "completed",
        color: "emerald",
        description: "Health checks and metrics collection active",
        details: {
            metrics: "CPU, Memory, Latency",
            alerts: "2 triggered",
            duration: "continuous",
            timestamp: "11:32 AM",
        },
    },
    {
        id: "sre",
        label: "SRE Agent",
        icon: Shield,
        status: "active",
        color: "cyan",
        description: "Investigating high CPU on staging-api-1",
        details: {
            incident: "INC-2847",
            severity: "High",
            action: "Auto-scaling evaluation",
            timestamp: "12:04 PM",
        },
    },
    {
        id: "refactor",
        label: "Code Refactor",
        icon: Code2,
        status: "pending",
        color: "gray",
        description: "Waiting for SRE Agent to identify code issues",
        details: {
            queue: "3 files pending",
            bugsPending: "2 detected",
            autoFix: "Ready",
            timestamp: "—",
        },
    },
    {
        id: "testing",
        label: "Testing Agent",
        icon: TestTube2,
        status: "pending",
        color: "gray",
        description: "Will validate all code changes after refactoring",
        details: {
            suites: "5 ready",
            tests: "1,247 total",
            coverage: "Target: 95%",
            timestamp: "—",
        },
    },
    {
        id: "redeploy",
        label: "Redeploy",
        icon: Server,
        status: "pending",
        color: "gray",
        description: "Rolling update with zero-downtime deployment",
        details: {
            strategy: "Rolling update",
            rollback: "Auto on failure",
            healthCheck: "Enabled",
            timestamp: "—",
        },
    },
];

const executionLog = [
    { time: "11:30:00", event: "Deployment v2.4.1 initiated", agent: "System" },
    { time: "11:32:34", event: "All replicas healthy, monitoring started", agent: "System" },
    { time: "11:45:12", event: "Latency spike detected on /api/users", agent: "Monitor" },
    { time: "11:52:00", event: "SRE Agent activated — investigating incident", agent: "SRE Agent" },
    { time: "12:00:15", event: "Root cause: memory leak in auth-service", agent: "SRE Agent" },
    { time: "12:04:23", event: "High CPU on staging-api-1 — auto-scaling triggered", agent: "SRE Agent" },
];

const colorMap: Record<string, { bg: string; border: string; text: string; glow: string }> = {
    emerald: { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-400", glow: "shadow-[0_0_30px_rgba(16,185,129,0.3)]" },
    cyan: { bg: "bg-cyan-500/10", border: "border-cyan-500/30", text: "text-cyan-400", glow: "shadow-[0_0_30px_rgba(6,182,212,0.3)]" },
    gray: { bg: "bg-white/5", border: "border-white/10", text: "text-muted-foreground", glow: "" },
};

const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } },
};

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
};

export default function PipelinePage() {
    const [selectedStage, setSelectedStage] = useState<string>("sre");

    const selected = pipelineStages.find((s) => s.id === selectedStage)!;
    const selectedColor = colorMap[selected.color];

    return (
        <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="space-y-6"
        >
            {/* Header */}
            <motion.div variants={itemVariants} className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                        <GitBranch className="w-6 h-6 text-amber-400" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">Pipeline Workflow</h1>
                        <p className="text-muted-foreground text-sm">
                            End-to-end deployment pipeline with AI agent orchestration
                        </p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button className="bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all">
                        <Eye className="w-4 h-4 mr-2" /> Watch Live
                    </Button>
                </div>
            </motion.div>

            {/* Pipeline Visualization */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5 overflow-hidden">
                    <CardContent className="p-8">
                        <div className="flex items-center justify-between relative">
                            {/* Connection line behind everything */}
                            <div className="absolute top-8 left-8 right-8 h-0.5 bg-white/5 z-0" />

                            {pipelineStages.map((stage, i) => {
                                const colors = colorMap[stage.color];
                                const isSelected = selectedStage === stage.id;

                                return (
                                    <div key={stage.id} className="relative z-10 flex flex-col items-center">
                                        {/* Connector line progress */}
                                        {i > 0 && (
                                            <div className="absolute top-8 right-full w-full h-0.5 -mr-px">
                                                {stage.status === "completed" && (
                                                    <div className="h-full bg-emerald-500/50" />
                                                )}
                                                {stage.status === "active" && (
                                                    <motion.div
                                                        className="h-full bg-gradient-to-r from-emerald-500/50 to-cyan-500/50"
                                                        animate={{ opacity: [0.4, 1, 0.4] }}
                                                        transition={{ duration: 2, repeat: Infinity }}
                                                    />
                                                )}
                                            </div>
                                        )}

                                        <motion.button
                                            onClick={() => setSelectedStage(stage.id)}
                                            whileHover={{ scale: 1.1 }}
                                            whileTap={{ scale: 0.95 }}
                                            animate={
                                                stage.status === "active"
                                                    ? {
                                                        boxShadow: [
                                                            "0 0 0px rgba(6,182,212,0)",
                                                            "0 0 30px rgba(6,182,212,0.4)",
                                                            "0 0 0px rgba(6,182,212,0)",
                                                        ],
                                                    }
                                                    : {}
                                            }
                                            transition={
                                                stage.status === "active"
                                                    ? { duration: 2, repeat: Infinity }
                                                    : { type: "spring" }
                                            }
                                            className={`w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-300 ${colors.bg} ${colors.border} border-2 ${isSelected ? colors.glow : ""} ${isSelected ? "ring-2 ring-offset-2 ring-offset-[#030712]" : ""
                                                } ${isSelected && stage.color === "emerald" ? "ring-emerald-500/30" : ""} ${isSelected && stage.color === "cyan" ? "ring-cyan-500/30" : ""} ${isSelected && stage.color === "gray" ? "ring-white/10" : ""}`}
                                        >
                                            <stage.icon className={`w-7 h-7 ${colors.text}`} />
                                        </motion.button>

                                        <span className={`mt-3 text-xs font-medium ${colors.text}`}>
                                            {stage.label}
                                        </span>

                                        {stage.status === "completed" && (
                                            <CheckCircle2 className="w-4 h-4 text-emerald-400 mt-1" />
                                        )}
                                        {stage.status === "active" && (
                                            <motion.div
                                                animate={{ scale: [1, 1.3, 1], opacity: [0.5, 1, 0.5] }}
                                                transition={{ duration: 1.5, repeat: Infinity }}
                                                className="w-2 h-2 rounded-full bg-cyan-400 mt-2"
                                            />
                                        )}
                                        {stage.status === "pending" && (
                                            <Clock className="w-3.5 h-3.5 text-muted-foreground/50 mt-1.5" />
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Selected Stage Details */}
            <motion.div variants={itemVariants} className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card className={`bg-card border ${selectedColor.border} transition-all duration-300`}>
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <selected.icon className={`w-5 h-5 ${selectedColor.text}`} />
                            {selected.label} — Details
                            <Badge className={`ml-auto text-[10px] ${selectedColor.bg} ${selectedColor.text} border-0`}>
                                {selected.status}
                            </Badge>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <p className="text-sm text-muted-foreground">{selected.description}</p>
                        <div className="grid grid-cols-2 gap-3">
                            {Object.entries(selected.details).map(([key, value]) => (
                                <div key={key} className="p-3 rounded-lg bg-white/5 border border-white/5">
                                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{key}</p>
                                    <p className="text-sm font-medium text-white mt-1">{value}</p>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                {/* Execution Log */}
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Zap className="w-4 h-4 text-amber-400" />
                            Execution Log
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-3">
                            {executionLog.map((log, i) => (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: i * 0.08 }}
                                    className="flex items-start gap-3 p-2 rounded-lg hover:bg-white/5 transition-colors"
                                >
                                    <span className="text-[10px] text-muted-foreground font-mono shrink-0 mt-0.5 w-16">
                                        {log.time}
                                    </span>
                                    <div>
                                        <p className="text-sm text-white">{log.event}</p>
                                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 mt-1 bg-white/5 text-muted-foreground border-0">
                                            {log.agent}
                                        </Badge>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>
        </motion.div>
    );
}
