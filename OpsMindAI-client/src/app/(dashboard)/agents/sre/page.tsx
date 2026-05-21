"use client";

import { motion } from "framer-motion";
import {
    Shield,
    Server,
    Activity,
    AlertTriangle,
    CheckCircle2,
    RefreshCw,
    RotateCcw,
    Terminal,
    Cpu,
    HardDrive,
    Wifi,
    Clock,
    ArrowDownUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

const servers = [
    { name: "prod-api-1", status: "healthy", cpu: 34, memory: 62, uptime: "14d 7h" },
    { name: "prod-api-2", status: "healthy", cpu: 45, memory: 58, uptime: "14d 7h" },
    { name: "prod-db-1", status: "warning", cpu: 82, memory: 91, uptime: "7d 2h" },
    { name: "prod-worker-1", status: "healthy", cpu: 23, memory: 44, uptime: "14d 7h" },
    { name: "prod-cache-1", status: "healthy", cpu: 12, memory: 38, uptime: "21d 3h" },
    { name: "staging-api-1", status: "critical", cpu: 98, memory: 95, uptime: "0d 0h" },
];

const incidentTimeline = [
    {
        time: "12:04 PM",
        title: "High CPU detected on staging-api-1",
        type: "alert",
        status: "investigating",
    },
    {
        time: "11:52 AM",
        title: "Auto-rollback triggered for v2.4.1",
        type: "rollback",
        status: "completed",
    },
    {
        time: "11:30 AM",
        title: "Memory leak detected on prod-db-1",
        type: "alert",
        status: "resolved",
    },
    {
        time: "10:15 AM",
        title: "Server prod-api-1 restarted successfully",
        type: "restart",
        status: "completed",
    },
    {
        time: "09:45 AM",
        title: "Deployment v2.4.0 health check passed",
        type: "deploy",
        status: "completed",
    },
];

const logLines = [
    { time: "12:04:23", level: "ERROR", msg: "[staging-api-1] OOMKilled: container exceeded memory limit" },
    { time: "12:04:22", level: "WARN", msg: "[staging-api-1] Memory usage at 95% — pod restart imminent" },
    { time: "12:04:20", level: "INFO", msg: "[sre-agent] Analyzing container metrics for staging-api-1" },
    { time: "12:04:18", level: "INFO", msg: "[sre-agent] Auto-scaling evaluation triggered" },
    { time: "12:04:15", level: "WARN", msg: "[prod-db-1] Slow query detected: 2.3s on users_table" },
    { time: "12:04:10", level: "INFO", msg: "[sre-agent] Health check passed for prod-api-1, prod-api-2" },
    { time: "12:04:05", level: "INFO", msg: "[sre-agent] Monitoring 6 servers, 2 alerts active" },
    { time: "12:03:58", level: "INFO", msg: "[prod-worker-1] Background job queue: 42 pending, 0 failed" },
];

const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
};

export default function SREAgentPage() {
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
                    <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
                        <Shield className="w-6 h-6 text-cyan-400" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">SRE Agent</h1>
                        <p className="text-muted-foreground text-sm">
                            Infrastructure monitoring, incident response & auto-recovery
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Badge className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1.5" />
                        Active
                    </Badge>
                </div>
            </motion.div>

            {/* Quick Actions */}
            <motion.div variants={itemVariants} className="flex gap-3 flex-wrap">
                <Button className="bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 hover:shadow-[0_0_20px_rgba(6,182,212,0.2)] transition-all">
                    <RefreshCw className="w-4 h-4 mr-2" /> Restart Server
                </Button>
                <Button className="bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 hover:shadow-[0_0_20px_rgba(245,158,11,0.2)] transition-all">
                    <RotateCcw className="w-4 h-4 mr-2" /> Rollback
                </Button>
                <Button className="bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 hover:shadow-[0_0_20px_rgba(139,92,246,0.2)] transition-all">
                    <Terminal className="w-4 h-4 mr-2" /> View Logs
                </Button>
            </motion.div>

            {/* Server Status Grid */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Server className="w-4 h-4 text-cyan-400" />
                            Server Status
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
                                    className={`p-4 rounded-xl border transition-all duration-300 hover:scale-[1.02] ${server.status === "healthy"
                                            ? "bg-emerald-500/5 border-emerald-500/10 hover:border-emerald-500/30"
                                            : server.status === "warning"
                                                ? "bg-amber-500/5 border-amber-500/10 hover:border-amber-500/30"
                                                : "bg-rose-500/5 border-rose-500/10 hover:border-rose-500/30"
                                        }`}
                                >
                                    <div className="flex items-center justify-between mb-3">
                                        <div className="flex items-center gap-2">
                                            <Server className={`w-4 h-4 ${server.status === "healthy" ? "text-emerald-400" : server.status === "warning" ? "text-amber-400" : "text-rose-400"
                                                }`} />
                                            <span className="text-sm font-medium text-white">{server.name}</span>
                                        </div>
                                        <Badge variant="secondary" className={`text-[10px] px-1.5 py-0 border-0 ${server.status === "healthy" ? "bg-emerald-500/10 text-emerald-400" :
                                                server.status === "warning" ? "bg-amber-500/10 text-amber-400" :
                                                    "bg-rose-500/10 text-rose-400"
                                            }`}>
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

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Incident Timeline */}
                <motion.div variants={itemVariants}>
                    <Card className="bg-card border-white/5 h-full">
                        <CardHeader>
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <Activity className="w-4 h-4 text-amber-400" />
                                Incident Timeline
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="relative space-y-4">
                                <div className="absolute left-[7px] top-2 bottom-2 w-px bg-white/5" />
                                {incidentTimeline.map((incident, i) => (
                                    <motion.div
                                        key={i}
                                        initial={{ opacity: 0, x: -10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: i * 0.1 }}
                                        className="relative flex items-start gap-4 pl-6"
                                    >
                                        <div className={`absolute left-0 top-1 w-3.5 h-3.5 rounded-full border-2 ${incident.status === "investigating" ? "bg-amber-500 border-amber-400" :
                                                incident.status === "resolved" ? "bg-emerald-500 border-emerald-400" :
                                                    "bg-cyan-500 border-cyan-400"
                                            }`} />
                                        <div className="flex-1">
                                            <p className="text-sm text-white">{incident.title}</p>
                                            <div className="flex items-center gap-2 mt-1">
                                                <span className="text-[10px] text-muted-foreground">{incident.time}</span>
                                                <Badge variant="secondary" className={`text-[10px] px-1.5 py-0 border-0 ${incident.status === "investigating" ? "bg-amber-500/10 text-amber-400" :
                                                        incident.status === "resolved" ? "bg-emerald-500/10 text-emerald-400" :
                                                            "bg-cyan-500/10 text-cyan-400"
                                                    }`}>
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

                {/* Live Log Viewer */}
                <motion.div variants={itemVariants}>
                    <Card className="bg-card border-white/5 h-full">
                        <CardHeader>
                            <CardTitle className="text-white text-base flex items-center gap-2">
                                <Terminal className="w-4 h-4 text-emerald-400" />
                                Live Logs
                                <motion.div
                                    animate={{ opacity: [0.3, 1, 0.3] }}
                                    transition={{ duration: 1.5, repeat: Infinity }}
                                    className="w-2 h-2 rounded-full bg-emerald-500 ml-2"
                                />
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="bg-[#0a0f1a] rounded-xl p-4 font-mono text-xs space-y-1.5 max-h-[320px] overflow-y-auto">
                                {logLines.map((line, i) => (
                                    <motion.div
                                        key={i}
                                        initial={{ opacity: 0, x: -5 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: i * 0.08 }}
                                        className="flex gap-2"
                                    >
                                        <span className="text-muted-foreground shrink-0">{line.time}</span>
                                        <span className={`shrink-0 font-semibold ${line.level === "ERROR" ? "text-rose-400" :
                                                line.level === "WARN" ? "text-amber-400" :
                                                    "text-emerald-400"
                                            }`}>
                                            [{line.level.padEnd(5)}]
                                        </span>
                                        <span className="text-white/80">{line.msg}</span>
                                    </motion.div>
                                ))}
                                <motion.span
                                    animate={{ opacity: [0, 1, 0] }}
                                    transition={{ duration: 1, repeat: Infinity }}
                                    className="text-cyan-400"
                                >
                                    █
                                </motion.span>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </div>
        </motion.div>
    );
}
