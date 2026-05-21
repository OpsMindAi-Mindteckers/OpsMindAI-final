"use client";

import { AnimatedBackground } from "@/components/animated-background";

export default function AuthLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <div className="relative min-h-screen flex items-center justify-center overflow-hidden bg-[#030712]">
            <AnimatedBackground />
            {/* Grid overlay */}
            <div className="absolute inset-0 bg-grid z-0" />
            {/* Gradient overlays */}
            <div className="absolute top-0 left-0 w-[600px] h-[600px] bg-cyan-500/5 rounded-full blur-[128px] -translate-x-1/2 -translate-y-1/2" />
            <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-violet-500/5 rounded-full blur-[128px] translate-x-1/2 translate-y-1/2" />
            <div className="relative z-10 w-full">{children}</div>
        </div>
    );
}
