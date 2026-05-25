"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
    Settings as SettingsIcon, Bell, Key, User, Save, CheckCircle2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useState, useEffect } from "react";

const container = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.08 } } };
const item      = { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } };

interface Profile { name: string; email: string; role: string; }

interface NotifPref {
    label:   string;
    desc:    string;
    key:     string;
    checked: boolean;
}

const DEFAULT_PROFILE: Profile = { name: "Admin User", email: "admin@opsmind.ai", role: "DevOps Lead" };

const DEFAULT_NOTIFS: NotifPref[] = [
    { label: "Incident alerts",        desc: "Get notified when SRE Agent detects issues",        key: "incidents",  checked: true  },
    { label: "Code fix notifications", desc: "When Code Refactor Agent applies patches",           key: "codefixes",  checked: true  },
    { label: "Test results",           desc: "Testing Agent completion reports",                   key: "tests",      checked: false },
    { label: "Pipeline status",        desc: "Deployment & rollback updates",                      key: "pipeline",   checked: true  },
];

export default function SettingsPage() {
    const [profile, setProfile] = useState<Profile>(DEFAULT_PROFILE);
    const [notifs, setNotifs]   = useState<NotifPref[]>(DEFAULT_NOTIFS);
    const [openaiKey, setOpenaiKey]   = useState("sk-proj-xxxxxxxxxxxx");
    const [cloudToken, setCloudToken] = useState("gcp_xxxxxxxxxxxx");
    const [saved, setSaved] = useState(false);
    const [saving, setSaving] = useState(false);

    // Load saved profile on mount
    useEffect(() => {
        try {
            const stored = localStorage.getItem("opsmind_profile");
            if (stored) {
                const p = JSON.parse(stored) as Partial<Profile>;
                setProfile(prev => ({ ...prev, ...p }));
            }
            const storedNotifs = localStorage.getItem("opsmind_notifs");
            if (storedNotifs) setNotifs(JSON.parse(storedNotifs));
        } catch { /* ignore */ }
    }, []);

    function toggleNotif(key: string) {
        setNotifs(prev => prev.map(n => n.key === key ? { ...n, checked: !n.checked } : n));
    }

    async function handleSave() {
        setSaving(true);
        // Persist to localStorage so Navbar and other components can read it
        localStorage.setItem("opsmind_profile", JSON.stringify(profile));
        localStorage.setItem("opsmind_notifs",  JSON.stringify(notifs));
        // Dispatch event so Navbar re-reads profile without page reload
        window.dispatchEvent(new Event("opsmind_profile_update"));

        await new Promise(r => setTimeout(r, 600)); // brief visual delay
        setSaving(false);
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
    }

    return (
        <motion.div variants={container} initial="hidden" animate="visible" className="space-y-6 max-w-3xl">

            {/* Header */}
            <motion.div variants={item} className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center">
                    <SettingsIcon className="w-6 h-6 text-muted-foreground" />
                </div>
                <div>
                    <h1 className="text-2xl font-bold text-white">Settings</h1>
                    <p className="text-muted-foreground text-sm">Manage your account and preferences</p>
                </div>
            </motion.div>

            {/* Profile */}
            <motion.div variants={item}>
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
                                <Input
                                    value={profile.name}
                                    onChange={e => setProfile(p => ({ ...p, name: e.target.value }))}
                                    className="bg-white/5 border-white/10 text-white h-10"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-white/80 text-sm">Email</Label>
                                <Input
                                    value={profile.email}
                                    onChange={e => setProfile(p => ({ ...p, email: e.target.value }))}
                                    className="bg-white/5 border-white/10 text-white h-10"
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-white/80 text-sm">Role</Label>
                            <Input
                                value={profile.role}
                                onChange={e => setProfile(p => ({ ...p, role: e.target.value }))}
                                className="bg-white/5 border-white/10 text-white h-10"
                            />
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Notifications */}
            <motion.div variants={item}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Bell className="w-4 h-4 text-amber-400" /> Notifications
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-1">
                        {notifs.map(n => (
                            <div key={n.key} className="flex items-center justify-between p-3 rounded-lg hover:bg-white/5 transition-colors">
                                <div>
                                    <p className="text-sm text-white">{n.label}</p>
                                    <p className="text-xs text-muted-foreground">{n.desc}</p>
                                </div>
                                <Checkbox
                                    checked={n.checked}
                                    onCheckedChange={() => toggleNotif(n.key)}
                                    className="border-white/20 data-[state=checked]:bg-cyan-500 data-[state=checked]:border-cyan-500"
                                />
                            </div>
                        ))}
                    </CardContent>
                </Card>
            </motion.div>

            {/* API Keys */}
            <motion.div variants={item}>
                <Card className="bg-card border-white/5">
                    <CardHeader>
                        <CardTitle className="text-white text-base flex items-center gap-2">
                            <Key className="w-4 h-4 text-violet-400" /> API Keys
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <Label className="text-white/80 text-sm">OpenAI API Key</Label>
                            <Input
                                type="password"
                                value={openaiKey}
                                onChange={e => setOpenaiKey(e.target.value)}
                                className="bg-white/5 border-white/10 text-white font-mono h-10"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-white/80 text-sm">Cloud Provider Token</Label>
                            <Input
                                type="password"
                                value={cloudToken}
                                onChange={e => setCloudToken(e.target.value)}
                                className="bg-white/5 border-white/10 text-white font-mono h-10"
                            />
                        </div>
                    </CardContent>
                </Card>
            </motion.div>

            {/* Save row */}
            <motion.div variants={item} className="flex items-center gap-4">
                <Button
                    onClick={handleSave}
                    disabled={saving}
                    className="bg-gradient-to-r from-cyan-500 to-violet-500 hover:from-cyan-400 hover:to-violet-400 text-white font-semibold shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/30 transition-all"
                >
                    <Save className="w-4 h-4 mr-2" />
                    {saving ? "Saving…" : "Save Settings"}
                </Button>

                <AnimatePresence>
                    {saved && (
                        <motion.div
                            initial={{ opacity: 0, x: -8 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -8 }}
                            className="flex items-center gap-1.5 text-sm text-emerald-400"
                        >
                            <CheckCircle2 className="w-4 h-4" />
                            Saved — navbar updated
                        </motion.div>
                    )}
                </AnimatePresence>
            </motion.div>
        </motion.div>
    );
}
