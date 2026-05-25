"use client";

import { Sidebar } from "@/components/sidebar";
import { Navbar }  from "@/components/navbar";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname } from "next/navigation";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();

    return (
        <div className="flex h-screen overflow-hidden" style={{ background: "#020408" }}>

            {/* Global ambient orbs */}
            <div className="fixed inset-0 pointer-events-none z-0">
                <motion.div
                    animate={{ x: [0, 40, 0], y: [0, -30, 0], scale: [1, 1.1, 1] }}
                    transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute top-0 right-1/4 w-[600px] h-[600px] rounded-full"
                    style={{ background: "radial-gradient(circle, rgba(6,182,212,0.04) 0%, transparent 70%)", filter: "blur(40px)" }}
                />
                <motion.div
                    animate={{ x: [0, -30, 0], y: [0, 40, 0], scale: [1, 1.15, 1] }}
                    transition={{ duration: 25, repeat: Infinity, ease: "easeInOut", delay: 5 }}
                    className="absolute bottom-1/4 left-1/4 w-[500px] h-[500px] rounded-full"
                    style={{ background: "radial-gradient(circle, rgba(139,92,246,0.04) 0%, transparent 70%)", filter: "blur(40px)" }}
                />
                <motion.div
                    animate={{ x: [0, 20, 0], y: [0, 20, 0] }}
                    transition={{ duration: 18, repeat: Infinity, ease: "easeInOut", delay: 8 }}
                    className="absolute top-1/2 right-0 w-[400px] h-[400px] rounded-full"
                    style={{ background: "radial-gradient(circle, rgba(232,121,249,0.03) 0%, transparent 70%)", filter: "blur(40px)" }}
                />
            </div>

            {/* Animated grid */}
            <div className="fixed inset-0 pointer-events-none z-0 bg-grid opacity-50" />

            <Sidebar />

            <div className="flex-1 flex flex-col overflow-hidden relative z-10">
                <Navbar />

                <main className="flex-1 overflow-y-auto">
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={pathname}
                            initial={{ opacity: 0, y: 16, filter: "blur(4px)" }}
                            animate={{ opacity: 1, y: 0,  filter: "blur(0px)" }}
                            exit={{    opacity: 0, y: -8,  filter: "blur(4px)" }}
                            transition={{ duration: 0.4, ease: [0.23, 1, 0.32, 1] }}
                            className="p-6 min-h-full"
                        >
                            {children}
                        </motion.div>
                    </AnimatePresence>
                </main>
            </div>
        </div>
    );
}
