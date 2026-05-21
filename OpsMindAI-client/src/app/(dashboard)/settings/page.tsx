"use client";

import { motion } from "framer-motion";
import {
    Settings as SettingsIcon,
    Bell,
    Shield,
    Palette,
    Globe,
    Key,
    User,
    Monitor,
    Save,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";

const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};
const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
};

export default function SettingsPage() {
    return (
        <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
            className="space-y-6 max-w-3xl"
        >
            <motion.div variants={itemVariants} className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
                    <SettingsIcon className="w-6 h-6 text-muted-foreground" />
                </div>
                <div>
                    <h1 className="text-2xl font-bold text-white">Settings</h1>
                    <p className="text-muted-foreground text-sm">Manage your account and preferences</p>
                </div>
            </motion.div>

            {/* Profile */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <User className="w-4 h-4 text-cyan-400" /> Profile
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label className="text-white/80 text-sm">Full Name</Label>
                                <Input defaultValue="Admin User" className="bg-white/5 border-white/10 text-white h-10" />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-white/80 text-sm">Email</Label>
                                <Input defaultValue="admin@opsmind.ai" className="bg-white/5 border-white/10 text-white h-10" />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-white/80 text-sm">Role</Label>
                            <Input defaultValue="DevOps Lead" className="bg-white/5 border-white/10 text-white h-10" />
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Notifications */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Bell className="w-4 h-4 text-amber-400" /> Notifications
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {[
                            { label: "Incident alerts", desc: "Get notified when SRE Agent detects issues", checked: true },
                            { label: "Code fix notifications", desc: "When Code Refactor Agent applies patches", checked: true },
                            { label: "Test results", desc: "Testing Agent completion reports", checked: false },
                            { label: "Pipeline status", desc: "Deployment & rollback updates", checked: true },
                        ].map((n) => (
                            <div key={n.label} className="flex items-center justify-between p-3 rounded-lg hover:bg-white/5 transition-colors">
                                <div>
                                    <p className="text-sm text-white">{n.label}</p>
                                    <p className="text-xs text-muted-foreground">{n.desc}</p>
                                </div>
                                <Checkbox defaultChecked={n.checked} className="border-white/20 data-[state=checked]:bg-cyan-500 data-[state=checked]:border-cyan-500" />
                            </div>
                        ))}
                    </CardContent>
                </Card>
            </motion.div>

            {/* API Keys */}
            <motion.div variants={itemVariants}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Key className="w-4 h-4 text-violet-400" /> API Keys
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <Label className="text-white/80 text-sm">OpenAI API Key</Label>
                            <Input type="password" defaultValue="sk-proj-xxxxxxxxxxxx" className="bg-white/5 border-white/10 text-white font-mono h-10" />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-white/80 text-sm">Cloud Provider Token</Label>
                            <Input type="password" defaultValue="gcp_xxxxxxxxxxxx" className="bg-white/5 border-white/10 text-white font-mono h-10" />
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            <motion.div variants={itemVariants}>
                <Button className="bg-gradient-to-r from-cyan-500 to-violet-500 hover:from-cyan-400 hover:to-violet-400 text-white font-semibold shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/30 transition-all">
                    <Save className="w-4 h-4 mr-2" /> Save Settings
                </Button>
            </motion.div>
        </motion.div>
    );
}
