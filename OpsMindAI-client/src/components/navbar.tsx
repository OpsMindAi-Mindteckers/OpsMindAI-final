"use client";

import { motion } from "framer-motion";
import { Bell, Search, Sparkles } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

export function Navbar() {
    return (
        <motion.header
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="h-16 border-b border-white/5 glass flex items-center justify-between px-6 z-10"
        >
            {/* Search */}
            <div className="relative w-80">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                    placeholder="Search agents, pipelines, logs..."
                    className="pl-10 bg-white/5 border-white/10 focus:border-cyan-500/30 focus:ring-cyan-500/10 text-white placeholder:text-muted-foreground/60 h-9 text-sm"
                />
            </div>

            {/* Right side */}
            <div className="flex items-center gap-4">
                {/* AI Status */}
                <motion.div
                    animate={{ opacity: [0.5, 1, 0.5] }}
                    transition={{ duration: 2, repeat: Infinity }}
                    className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20"
                >
                    <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="text-xs font-medium text-emerald-400">
                        AI Active
                    </span>
                </motion.div>

                {/* Notifications */}
                <button className="relative p-2 rounded-lg hover:bg-white/5 transition-colors group">
                    <Bell className="w-5 h-5 text-muted-foreground group-hover:text-white transition-colors" />
                    <Badge className="absolute -top-0.5 -right-0.5 w-4 h-4 p-0 flex items-center justify-center text-[10px] bg-rose-500 border-0 text-white">
                        3
                    </Badge>
                </button>

                {/* User */}
                <div className="flex items-center gap-3 pl-3 border-l border-white/10">
                    <div className="hidden sm:block text-right">
                        <p className="text-sm font-medium text-white">Admin User</p>
                        <p className="text-xs text-muted-foreground">DevOps Lead</p>
                    </div>
                    <Avatar className="w-8 h-8 border border-white/10">
                        <AvatarFallback className="bg-gradient-to-br from-cyan-500 to-violet-500 text-white text-xs font-bold">
                            AU
                        </AvatarFallback>
                    </Avatar>
                </div>
            </div>
        </motion.header>
    );
}
