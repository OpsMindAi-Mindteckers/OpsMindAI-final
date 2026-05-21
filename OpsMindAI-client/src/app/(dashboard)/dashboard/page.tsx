"use client";

import { motion } from "framer-motion";
import {
    Shield,
    Code2,
    TestTube2,
    Activity,
    Server,
    GitBranch,
    CheckCircle2,
    AlertTriangle,
    Clock,
    ArrowUpRight,
    TrendingUp,
    Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    BarChart,
    Bar,
} from "recharts";

const incidentData = [
    { time: "00:00", resolved: 2, detected: 3 },
    { time: "04:00", resolved: 5, detected: 4 },
    { time: "08:00", resolved: 8, detected: 10 },
    { time: "12:00", resolved: 12, detected: 11 },
    { time: "16:00", resolved: 15, detected: 14 },
    { time: "20:00", resolved: 18, detected: 16 },
    { time: "Now", resolved: 22, detected: 19 },
];

const testData = [
    { name: "Mon", pass: 95, fail: 5 },
    { name: "Tue", pass: 92, fail: 8 },
    { name: "Wed", pass: 97, fail: 3 },
    { name: "Thu", pass: 88, fail: 12 },
    { name: "Fri", pass: 94, fail: 6 },
    { name: "Sat", pass: 99, fail: 1 },
    { name: "Sun", pass: 96, fail: 4 },
];

const agentCards = [
    {
        title: "SRE Agent",
        icon: Shield,
        status: "Active",
        statusColor: "bg-emerald-500",
        glowClass: "glow-cyan",
        borderColor: "border-cyan-500/20",
        iconColor: "text-cyan-400",
        bgGradient: "from-cyan-500/10 to-transparent",
        stats: { resolved: 47, uptime: "99.97%", mttr: "2.3m" },
        href: "/agents/sre",
    },
    {
        title: "Code Refactor",
        icon: Code2,
        status: "Processing",
        statusColor: "bg-amber-500",
        glowClass: "glow-emerald",
        borderColor: "border-emerald-500/20",
        iconColor: "text-emerald-400",
        bgGradient: "from-emerald-500/10 to-transparent",
        stats: { fixed: 23, quality: "A+", coverage: "94%" },
        href: "/agents/code-refactor",
    },
    {
        title: "Testing Agent",
        icon: TestTube2,
        status: "Running Tests",
        statusColor: "bg-violet-500",
        glowClass: "glow-violet",
        borderColor: "border-violet-500/20",
        iconColor: "text-violet-400",
        bgGradient: "from-violet-500/10 to-transparent",
        stats: { passed: 1247, suites: 42, coverage: "96%" },
        href: "/agents/testing",
    },
];

const recentActivity = [
    {
        icon: CheckCircle2,
        color: "text-emerald-400",
        title: "Server restored successfully",
        agent: "SRE Agent",
        time: "2 min ago",
    },
    {
        icon: Code2,
        color: "text-cyan-400",
        title: "Memory leak fixed in auth-service",
        agent: "Code Refactor",
        time: "8 min ago",
    },
    {
        icon: TestTube2,
        color: "text-violet-400",
        title: "Test suite #42 completed — 99% pass",
        agent: "Testing Agent",
        time: "15 min ago",
    },
    {
        icon: AlertTriangle,
        color: "text-amber-400",
        title: "High CPU usage detected on prod-3",
        agent: "SRE Agent",
        time: "23 min ago",
    },
    {
        icon: GitBranch,
        color: "text-rose-400",
        title: "Pipeline rollback triggered",
        agent: "SRE Agent",
        time: "31 min ago",
    },
    {
        icon: Zap,
        color: "text-emerald-400",
        title: "Auto-scaling applied to api-gateway",
        agent: "SRE Agent",
        time: "45 min ago",
    },
];

const pipelineSteps = [
    { label: "Deploy", status: "completed", icon: Server },
    { label: "Monitor", status: "completed", icon: Activity },
    { label: "SRE", status: "active", icon: Shield },
    { label: "Refactor", status: "pending", icon: Code2 },
    { label: "Test", status: "pending", icon: TestTube2 },
    { label: "Redeploy", status: "pending", icon: GitBranch },
];

const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: { staggerChildren: 0.1 },
    },
};

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
};

export default function DashboardPage() {
    return (
        <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="space-y-6"
        >
            {/* Header */}
            <motion.div variants={itemVariants} className="space-y-1">
                <h1 className="text-3xl font-bold text-white">
                    Command Center
                </h1>
                <p className="text-muted-foreground">
                    Real-time overview of all AI agents and system health
                </p>
            </motion.div>

            {/* Stats Row */}
            <motion.div variants={itemVariants} className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                    { label: "Active Agents", value: "3/3", icon: Zap, color: "text-cyan-400", change: "+0%" },
                    { label: "Incidents Today", value: "7", icon: AlertTriangle, color: "text-amber-400", change: "-23%" },
                    { label: "Deployments", value: "14", icon: GitBranch, color: "text-violet-400", change: "+12%" },
                    { label: "System Uptime", value: "99.97%", icon: TrendingUp, color: "text-emerald-400", change: "+0.02%" },
                ].map((stat) => (
                    <Card key={stat.label} className="bg-card border-white/5 hover:border-white/10 transition-all duration-300">
                        <CardContent className="p-4">
                            <div className="flex items-center justify-between">
                                <stat.icon className={`w-5 h-5 ${stat.color}`} />
                                <span className="text-xs text-emerald-400">{stat.change}</span>
                            </div>
                            <p className="text-2xl font-bold text-white mt-2">{stat.value}</p>
                            <p className="text-xs text-muted-foreground mt-1">{stat.label}</p>
                        </CardContent>
                    </Card>
                ))}
            </motion.div>

            {/* Agent Cards */}
            <motion.div variants={itemVariants} className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {agentCards.map((agent, i) => (
                    <Link key={agent.title} href={agent.href}>
                        <motion.div
                            whileHover={{ y: -4, scale: 1.01 }}
                            whileTap={{ scale: 0.99 }}
                            transition={{ type: "spring", stiffness: 400 }}
                        >
                            <Card
                                className={`bg-card border ${agent.borderColor} hover:${agent.glowClass} transition-all duration-500 cursor-pointer overflow-hidden relative`}
                            >
                                <div className={`absolute inset-0 bg-gradient-to-br ${agent.bgGradient} opacity-50`} />
                                <CardHeader className="relative pb-2">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <div className={`w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center ${agent.iconColor}`}>
                                                <agent.icon className="w-5 h-5" />
                                            </div>
                                            <div>
                                                <CardTitle className="text-base text-white">
                                                    {agent.title}
                                                </CardTitle>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <div className={`w-2 h-2 rounded-full ${agent.statusColor} animate-pulse`} />
                                            <span className="text-xs text-muted-foreground">
                                                {agent.status}
                                            </span>
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent className="relative">
                                    <div className="grid grid-cols-3 gap-2">
                                        {Object.entries(agent.stats).map(([key, value]) => (
                                            <div key={key} className="text-center p-2 rounded-lg bg-white/5">
                                                <p className="text-lg font-bold text-white">{value}</p>
                                                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                                                    {key}
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                    <div className="flex items-center justify-end mt-3 text-xs text-muted-foreground group-hover:text-white">
                                        <span className="flex items-center gap-1">
                                            View Details <ArrowUpRight className="w-3 h-3" />
                                        </span>
                                    </div>
                                </CardContent>
                            </Card>
                        </motion.div>
                    </Link>
                ))}
            </motion.div>

            {/* Pipeline Flow */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white flex items-center gap-2">
                            <GitBranch className="w-5 h-5 text-amber-400" />
                            Pipeline Flow
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex items-center justify-between px-4">
                            {pipelineSteps.map((step, i) => (
                                <div key={step.label} className="flex items-center">
                                    <div className="flex flex-col items-center gap-2">
                                        <motion.div
                                            animate={
                                                step.status === "active"
                                                    ? { scale: [1, 1.1, 1], boxShadow: ["0 0 0px rgba(6,182,212,0)", "0 0 20px rgba(6,182,212,0.4)", "0 0 0px rgba(6,182,212,0)"] }
                                                    : {}
                                            }
                                            transition={{ duration: 2, repeat: Infinity }}
                                            className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all ${step.status === "completed"
                                                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                                    : step.status === "active"
                                                        ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                                                        : "bg-white/5 text-muted-foreground border border-white/10"
                                                }`}
                                        >
                                            <step.icon className="w-5 h-5" />
                                        </motion.div>
                                        <span className={`text-xs font-medium ${step.status === "active" ? "text-cyan-400" : step.status === "completed" ? "text-emerald-400" : "text-muted-foreground"
                                            }`}>
                                            {step.label}
                                        </span>
                                    </div>
                                    {i < pipelineSteps.length - 1 && (
                                        <div className="flex-1 mx-3 h-px relative">
                                            <div className={`absolute inset-0 ${step.status === "completed" ? "bg-emerald-500/40" : "bg-white/10"
                                                }`} />
                                            {step.status === "active" && (
                                                <motion.div
                                                    className="absolute inset-y-0 left-0 bg-gradient-to-r from-cyan-500 to-transparent"
                                                    animate={{ width: ["0%", "100%", "0%"] }}
                                                    transition={{ duration: 2, repeat: Infinity }}
                                                />
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Charts and Activity */}
            <motion.div variants={itemVariants} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* Incident Chart */}
                <Card className="bg-card border-white/5 lg:col-span-2">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Activity className="w-4 h-4 text-cyan-400" />
                            Incident Resolution
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={220}>
                            <AreaChart data={incidentData}>
                                <defs>
                                    <linearGradient id="colorResolved" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="colorDetected" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.05)" />
                                <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
                                <YAxis stroke="#64748b" fontSize={11} />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: "#0f172a",
                                        border: "1px solid rgba(148,163,184,0.1)",
                                        borderRadius: "12px",
                                        color: "#fff",
                                        fontSize: "12px",
                                    }}
                                />
                                <Area type="monotone" dataKey="resolved" stroke="#06b6d4" fill="url(#colorResolved)" strokeWidth={2} />
                                <Area type="monotone" dataKey="detected" stroke="#8b5cf6" fill="url(#colorDetected)" strokeWidth={2} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                {/* Activity Feed */}
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Clock className="w-4 h-4 text-violet-400" />
                            Recent Activity
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {recentActivity.map((item, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: i * 0.1 }}
                                className="flex items-start gap-3 p-2 rounded-lg hover:bg-white/5 transition-colors"
                            >
                                <item.icon className={`w-4 h-4 mt-0.5 shrink-0 ${item.color}`} />
                                <div className="min-w-0">
                                    <p className="text-sm text-white truncate">{item.title}</p>
                                    <div className="flex items-center gap-2 mt-0.5">
                                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 bg-white/5 text-muted-foreground border-0">
                                            {item.agent}
                                        </Badge>
                                        <span className="text-[10px] text-muted-foreground">{item.time}</span>
                                    </div>
                                </div>
                            </motion.div>
                        ))}
                    </CardContent>
                </Card>
            </motion.div>

            {/* Test Results Chart */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <TestTube2 className="w-4 h-4 text-emerald-400" />
                            Weekly Test Pass Rate
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <ResponsiveContainer width="100%" height={180}>
                            <BarChart data={testData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.05)" />
                                <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
                                <YAxis stroke="#64748b" fontSize={11} />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: "#0f172a",
                                        border: "1px solid rgba(148,163,184,0.1)",
                                        borderRadius: "12px",
                                        color: "#fff",
                                        fontSize: "12px",
                                    }}
                                />
                                <Bar dataKey="pass" fill="#10b981" radius={[4, 4, 0, 0]} />
                                <Bar dataKey="fail" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>
            </motion.div>
        </motion.div>
    );
}
