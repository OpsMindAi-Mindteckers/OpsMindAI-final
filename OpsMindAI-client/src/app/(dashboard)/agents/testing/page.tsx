"use client";

import { motion } from "framer-motion";
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
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useState } from "react";

const testSuites = [
    {
        name: "Authentication Tests",
        total: 24,
        passed: 24,
        failed: 0,
        duration: "1.2s",
        status: "passed",
        tests: [
            { name: "should login with valid credentials", status: "passed", duration: "45ms" },
            { name: "should reject invalid password", status: "passed", duration: "32ms" },
            { name: "should refresh expired tokens", status: "passed", duration: "78ms" },
            { name: "should handle MFA correctly", status: "passed", duration: "120ms" },
        ],
    },
    {
        name: "API Gateway Tests",
        total: 18,
        passed: 17,
        failed: 1,
        duration: "3.4s",
        status: "failed",
        tests: [
            { name: "should route to correct service", status: "passed", duration: "23ms" },
            { name: "should handle rate limiting", status: "failed", duration: "1.2s" },
            { name: "should validate request schema", status: "passed", duration: "56ms" },
            { name: "should apply CORS headers", status: "passed", duration: "18ms" },
        ],
    },
    {
        name: "Database Integration",
        total: 32,
        passed: 32,
        failed: 0,
        duration: "5.1s",
        status: "passed",
        tests: [
            { name: "should create user record", status: "passed", duration: "89ms" },
            { name: "should handle concurrent writes", status: "passed", duration: "234ms" },
            { name: "should rollback on failure", status: "passed", duration: "156ms" },
        ],
    },
    {
        name: "Notification Service",
        total: 15,
        passed: 14,
        failed: 1,
        duration: "2.8s",
        status: "failed",
        tests: [
            { name: "should send email notification", status: "passed", duration: "345ms" },
            { name: "should retry failed delivery", status: "failed", duration: "2.1s" },
            { name: "should batch notifications", status: "passed", duration: "67ms" },
        ],
    },
    {
        name: "Worker Queue Tests",
        total: 21,
        passed: 21,
        failed: 0,
        duration: "1.9s",
        status: "passed",
        tests: [
            { name: "should process jobs in order", status: "passed", duration: "78ms" },
            { name: "should handle job failures", status: "passed", duration: "145ms" },
            { name: "should scale workers dynamically", status: "passed", duration: "234ms" },
        ],
    },
];

const overallProgress = 87;
const totalTests = 1247;
const totalPassed = 1240;
const totalFailed = 7;

const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
};

export default function TestingAgentPage() {
    const [expandedSuite, setExpandedSuite] = useState<string | null>("API Gateway Tests");

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
                    <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
                        <TestTube2 className="w-6 h-6 text-violet-400" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-white">Testing Agent</h1>
                        <p className="text-muted-foreground text-sm">
                            Automated test execution, coverage analysis & validation
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button className="bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 hover:shadow-[0_0_20px_rgba(139,92,246,0.2)] transition-all">
                        <Play className="w-4 h-4 mr-2" /> Run All Tests
                    </Button>
                </div>
            </motion.div>

            {/* Progress Bar */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardContent className="p-6">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-sm font-medium text-white">Overall Test Progress</span>
                            <span className="text-sm font-bold text-violet-400">{overallProgress}%</span>
                        </div>
                        <div className="relative">
                            <Progress value={overallProgress} className="h-3 [&>div]:bg-gradient-to-r [&>div]:from-violet-500 [&>div]:to-cyan-500" />
                            <motion.div
                                className="absolute inset-0 h-3 rounded-full bg-gradient-to-r from-violet-500/20 to-cyan-500/20"
                                animate={{ opacity: [0.3, 0.6, 0.3] }}
                                transition={{ duration: 2, repeat: Infinity }}
                            />
                        </div>
                        <div className="flex items-center justify-between mt-3 text-xs text-muted-foreground">
                            <span>Running suite 4 of 5...</span>
                            <div className="flex items-center gap-1">
                                <RotateCw className="w-3 h-3 animate-spin" />
                                <span>Estimated: 12s remaining</span>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Stats */}
            <motion.div variants={itemVariants} className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                    { label: "Total Tests", value: totalTests.toLocaleString(), icon: FileCheck, color: "text-cyan-400" },
                    { label: "Passed", value: totalPassed.toLocaleString(), icon: CheckCircle2, color: "text-emerald-400" },
                    { label: "Failed", value: totalFailed.toString(), icon: XCircle, color: "text-rose-400" },
                    { label: "Coverage", value: "96%", icon: BarChart3, color: "text-violet-400" },
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

            {/* Test Suites */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <FileCheck className="w-4 h-4 text-violet-400" />
                            Test Suites
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                        {testSuites.map((suite, i) => (
                            <motion.div
                                key={suite.name}
                                initial={{ opacity: 0, y: 5 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: i * 0.05 }}
                            >
                                <button
                                    onClick={() => setExpandedSuite(expandedSuite === suite.name ? null : suite.name)}
                                    className={`w-full p-4 rounded-xl border text-left transition-all duration-300 hover:scale-[1.005] ${suite.status === "passed"
                                            ? "bg-emerald-500/5 border-emerald-500/10 hover:border-emerald-500/20"
                                            : "bg-rose-500/5 border-rose-500/10 hover:border-rose-500/20"
                                        }`}
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            {expandedSuite === suite.name ? (
                                                <ChevronDown className="w-4 h-4 text-muted-foreground" />
                                            ) : (
                                                <ChevronRight className="w-4 h-4 text-muted-foreground" />
                                            )}
                                            {suite.status === "passed" ? (
                                                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                                            ) : (
                                                <XCircle className="w-4 h-4 text-rose-400" />
                                            )}
                                            <span className="text-sm font-medium text-white">{suite.name}</span>
                                        </div>
                                        <div className="flex items-center gap-4">
                                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                                                <Clock className="w-3 h-3" /> {suite.duration}
                                            </span>
                                            <div className="flex items-center gap-2 text-xs">
                                                <span className="text-emerald-400">{suite.passed} ✓</span>
                                                {suite.failed > 0 && (
                                                    <span className="text-rose-400">{suite.failed} ✗</span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </button>

                                {/* Expanded tests */}
                                {expandedSuite === suite.name && (
                                    <motion.div
                                        initial={{ height: 0, opacity: 0 }}
                                        animate={{ height: "auto", opacity: 1 }}
                                        exit={{ height: 0, opacity: 0 }}
                                        className="mt-1 ml-8 space-y-1"
                                    >
                                        {suite.tests.map((test, j) => (
                                            <motion.div
                                                key={test.name}
                                                initial={{ opacity: 0, x: -10 }}
                                                animate={{ opacity: 1, x: 0 }}
                                                transition={{ delay: j * 0.05 }}
                                                className="flex items-center justify-between p-2.5 rounded-lg bg-white/[0.02] border border-white/5"
                                            >
                                                <div className="flex items-center gap-2">
                                                    {test.status === "passed" ? (
                                                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                                                    ) : (
                                                        <XCircle className="w-3.5 h-3.5 text-rose-400" />
                                                    )}
                                                    <span className="text-xs text-white/80">{test.name}</span>
                                                </div>
                                                <span className="text-[10px] text-muted-foreground">{test.duration}</span>
                                            </motion.div>
                                        ))}
                                    </motion.div>
                                )}
                            </motion.div>
                        ))}
                    </CardContent>
                </Card>
            </motion.div>
        </motion.div>
    );
}
