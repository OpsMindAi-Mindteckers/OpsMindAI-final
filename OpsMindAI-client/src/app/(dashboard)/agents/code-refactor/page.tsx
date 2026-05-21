"use client";

import { motion } from "framer-motion";
import {
    Code2,
    Bug,
    CheckCircle2,
    AlertTriangle,
    Zap,
    FileCode,
    GitCompare,
    Sparkles,
    ArrowRight,
    BarChart3,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const bugDetections = [
    {
        id: 1,
        file: "auth-service/middleware.ts",
        line: 47,
        severity: "critical",
        type: "Memory Leak",
        description: "Unhandled promise rejection causing memory accumulation in JWT verification",
        status: "fixed",
    },
    {
        id: 2,
        file: "api-gateway/routes.ts",
        line: 132,
        severity: "high",
        type: "Race Condition",
        description: "Concurrent write without mutex lock on shared connection pool",
        status: "fixing",
    },
    {
        id: 3,
        file: "user-service/handlers.ts",
        line: 89,
        severity: "medium",
        type: "SQL Injection",
        description: "User input not sanitized in dynamic query construction",
        status: "detected",
    },
    {
        id: 4,
        file: "notification-service/queue.ts",
        line: 215,
        severity: "low",
        type: "Unused Variable",
        description: "Dead code path from deprecated notification channel",
        status: "detected",
    },
];

const codeBefore = `// auth-service/middleware.ts:47
async function verifyToken(token: string) {
  const decoded = jwt.verify(token, SECRET);
  // BUG: Promise chain not awaited,
  // event listeners accumulate
  db.query('SELECT * FROM sessions')
    .then(sessions => {
      sessions.forEach(s => {
        if (s.expired) delete s;
      });
    });
  return decoded;
}`;

const codeAfter = `// auth-service/middleware.ts:47
async function verifyToken(token: string) {
  const decoded = jwt.verify(token, SECRET);
  // FIXED: Properly awaited with cleanup
  const sessions = await db.query(
    'SELECT * FROM sessions'
  );
  await Promise.all(
    sessions
      .filter(s => s.expired)
      .map(s => db.deleteSession(s.id))
  );
  return decoded;
}`;

const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
};

export default function CodeRefactorPage() {
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
                    <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                        <Code2 className="w-6 h-6 text-emerald-400" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">Code Refactor Agent</h1>
                        <p className="text-muted-foreground text-sm">
                            Intelligent bug detection, auto-fix & code quality optimization
                        </p>
                    </div>
                </div>
                <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/20">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse mr-1.5" />
                    Processing
                </Badge>
            </motion.div>

            {/* Stats */}
            <motion.div variants={itemVariants} className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                    { label: "Bugs Detected", value: "23", icon: Bug, color: "text-rose-400" },
                    { label: "Auto-Fixed", value: "19", icon: Sparkles, color: "text-emerald-400" },
                    { label: "Code Quality", value: "A+", icon: BarChart3, color: "text-cyan-400" },
                    { label: "Coverage", value: "94%", icon: FileCode, color: "text-violet-400" },
                ].map((stat) => (
                    <Card key={stat.label} className="bg-card border-white/5">
                        <CardContent className="p-4">
                            <div className="flex items-center justify-between">
                                <stat.icon className={`w-5 h-5 ${stat.color}`} />
                            </div>
                            <p className="text-2xl font-bold text-white mt-2">{stat.value}</p>
                            <p className="text-xs text-muted-foreground mt-1">{stat.label}</p>
                        </CardContent>
                    </Card>
                ))}
            </motion.div>

            {/* Bug Detection List */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader className="flex flex-row items-center justify-between">
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Bug className="w-4 h-4 text-rose-400" />
                            Bug Detection Queue
                        </CardTitle>
                        <Button size="sm" className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 text-xs">
                            <Zap className="w-3 h-3 mr-1" />
                            Fix All
                        </Button>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {bugDetections.map((bug, i) => (
                            <motion.div
                                key={bug.id}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: i * 0.08 }}
                                className={`p-4 rounded-xl border transition-all hover:scale-[1.01] ${bug.severity === "critical" ? "bg-rose-500/5 border-rose-500/10" :
                                        bug.severity === "high" ? "bg-amber-500/5 border-amber-500/10" :
                                            bug.severity === "medium" ? "bg-yellow-500/5 border-yellow-500/10" :
                                                "bg-white/[0.02] border-white/5"
                                    }`}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2">
                                            <span className="text-sm font-medium text-white">{bug.type}</span>
                                            <Badge variant="secondary" className={`text-[10px] px-1.5 py-0 border-0 ${bug.severity === "critical" ? "bg-rose-500/10 text-rose-400" :
                                                    bug.severity === "high" ? "bg-amber-500/10 text-amber-400" :
                                                        bug.severity === "medium" ? "bg-yellow-500/10 text-yellow-400" :
                                                            "bg-white/5 text-muted-foreground"
                                                }`}>
                                                {bug.severity}
                                            </Badge>
                                        </div>
                                        <p className="text-xs text-muted-foreground">{bug.description}</p>
                                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                            <FileCode className="w-3 h-3" />
                                            <span className="font-mono">{bug.file}:{bug.line}</span>
                                        </div>
                                    </div>
                                    <Badge className={`text-[10px] shrink-0 ${bug.status === "fixed" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
                                            bug.status === "fixing" ? "bg-cyan-500/10 text-cyan-400 border-cyan-500/20" :
                                                "bg-amber-500/10 text-amber-400 border-amber-500/20"
                                        }`}>
                                        {bug.status === "fixed" ? <CheckCircle2 className="w-3 h-3 mr-1" /> :
                                            bug.status === "fixing" ? <motion.div animate={{ rotate: 360 }} transition={{ duration: 2, repeat: Infinity, ease: "linear" }}><Zap className="w-3 h-3 mr-1" /></motion.div> :
                                                <AlertTriangle className="w-3 h-3 mr-1" />}
                                        {bug.status}
                                    </Badge>
                                </div>
                            </motion.div>
                        ))}
                    </CardContent>
                </Card>
            </motion.div>

            {/* Code Diff View */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <GitCompare className="w-4 h-4 text-cyan-400" />
                            Code Comparison
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <Tabs defaultValue="before" className="w-full">
                            <TabsList className="bg-white/5 border border-white/10">
                                <TabsTrigger value="before" className="data-[state=active]:bg-rose-500/10 data-[state=active]:text-rose-400 text-xs">
                                    Before (Bug)
                                </TabsTrigger>
                                <TabsTrigger value="after" className="data-[state=active]:bg-emerald-500/10 data-[state=active]:text-emerald-400 text-xs">
                                    After (Fixed)
                                </TabsTrigger>
                            </TabsList>
                            <TabsContent value="before">
                                <div className="mt-3 bg-[#0a0f1a] rounded-xl p-4 font-mono text-xs border border-rose-500/10">
                                    <pre className="text-rose-300/80 whitespace-pre-wrap">{codeBefore}</pre>
                                </div>
                            </TabsContent>
                            <TabsContent value="after">
                                <div className="mt-3 bg-[#0a0f1a] rounded-xl p-4 font-mono text-xs border border-emerald-500/10">
                                    <pre className="text-emerald-300/80 whitespace-pre-wrap">{codeAfter}</pre>
                                </div>
                            </TabsContent>
                        </Tabs>
                    </CardContent>
                </Card>
            </motion.div>
        </motion.div>
    );
}
