"use client";

import { AnimatedBackground } from "@/components/animated-background";
import { motion } from "framer-motion";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="relative min-h-screen flex items-center justify-center overflow-hidden" style={{ background: "#020408" }}>
            <AnimatedBackground />

            {/* Dense grid overlay */}
            <div className="absolute inset-0 bg-grid-dense opacity-30 z-0" />

            {/* Corner frame decorations */}
            {[
                "top-0 left-0",
                "top-0 right-0 rotate-90",
                "bottom-0 right-0 rotate-180",
                "bottom-0 left-0 -rotate-90",
            ].map((pos, i) => (
                <div key={i} className={`absolute ${pos} w-24 h-24 pointer-events-none z-10`}>
                    <div className="absolute top-4 left-4 w-8 h-px bg-cyan-400/40" />
                    <div className="absolute top-4 left-4 w-px h-8 bg-cyan-400/40" />
                    <div className="absolute top-2 left-2 w-2 h-2 rounded-full bg-cyan-400/20 animate-pulse" />
                </div>
            ))}

            {/* Volumetric light sources */}
            <motion.div
                animate={{ scale: [1, 1.2, 1], opacity: [0.04, 0.08, 0.04] }}
                transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
                className="absolute -top-40 -left-40 w-[700px] h-[700px] rounded-full pointer-events-none"
                style={{ background: "radial-gradient(circle, rgba(6,182,212,1) 0%, transparent 70%)", filter: "blur(80px)" }}
            />
            <motion.div
                animate={{ scale: [1, 1.15, 1], opacity: [0.03, 0.07, 0.03] }}
                transition={{ duration: 10, repeat: Infinity, ease: "easeInOut", delay: 3 }}
                className="absolute -bottom-40 -right-40 w-[600px] h-[600px] rounded-full pointer-events-none"
                style={{ background: "radial-gradient(circle, rgba(139,92,246,1) 0%, transparent 70%)", filter: "blur(80px)" }}
            />
            <motion.div
                animate={{ scale: [1, 1.3, 1], opacity: [0.02, 0.05, 0.02] }}
                transition={{ duration: 12, repeat: Infinity, ease: "easeInOut", delay: 6 }}
                className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] rounded-full pointer-events-none"
                style={{ background: "radial-gradient(circle, rgba(232,121,249,1) 0%, transparent 70%)", filter: "blur(80px)" }}
            />

            {/* Horizontal scan line */}
            <motion.div
                animate={{ y: ["-100%", "100vh"] }}
                transition={{ duration: 6, repeat: Infinity, ease: "linear", repeatDelay: 4 }}
                className="absolute left-0 right-0 h-px pointer-events-none z-10"
                style={{ background: "linear-gradient(90deg, transparent, rgba(6,182,212,0.3), rgba(139,92,246,0.3), transparent)" }}
            />

            {/* HUD corners - top bar */}
            <div className="absolute top-0 left-0 right-0 h-px z-10"
                style={{ background: "linear-gradient(90deg, transparent 0%, rgba(6,182,212,0.3) 20%, rgba(6,182,212,0.6) 50%, rgba(6,182,212,0.3) 80%, transparent 100%)" }} />
            <div className="absolute bottom-0 left-0 right-0 h-px z-10"
                style={{ background: "linear-gradient(90deg, transparent 0%, rgba(139,92,246,0.3) 20%, rgba(139,92,246,0.6) 50%, rgba(139,92,246,0.3) 80%, transparent 100%)" }} />

            {/* HUD top-left tag */}
            <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.5, duration: 0.6 }}
                className="absolute top-4 left-6 z-10 flex items-center gap-2"
            >
                <motion.div
                    animate={{ opacity: [0.5, 1, 0.5] }}
                    transition={{ duration: 2, repeat: Infinity }}
                    className="w-1.5 h-1.5 rounded-full bg-cyan-400"
                />
                <span className="text-[10px] font-mono text-cyan-400/50 tracking-widest uppercase">OPSMIND.AI / AUTH</span>
            </motion.div>

            {/* HUD bottom-right tag */}
            <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.7, duration: 0.6 }}
                className="absolute bottom-4 right-6 z-10"
            >
                <span className="text-[10px] font-mono text-violet-400/40 tracking-widest uppercase">NEURAL OPS · v2.0</span>
            </motion.div>

            <div className="relative z-10 w-full">{children}</div>
        </div>
    );
}
