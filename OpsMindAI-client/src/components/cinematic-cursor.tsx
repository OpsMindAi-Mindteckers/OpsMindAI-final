"use client";

import { useEffect, useRef } from "react";

export function CinematicCursor() {
    const dotRef  = useRef<HTMLDivElement>(null);
    const ringRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        let rx = 0, ry = 0;
        let tx = 0, ty = 0;
        let raf: number;

        const onMove = (e: MouseEvent) => {
            tx = e.clientX;
            ty = e.clientY;
            if (dotRef.current) {
                dotRef.current.style.left = tx + "px";
                dotRef.current.style.top  = ty + "px";
            }
        };

        const tick = () => {
            rx += (tx - rx) * 0.12;
            ry += (ty - ry) * 0.12;
            if (ringRef.current) {
                ringRef.current.style.left = rx + "px";
                ringRef.current.style.top  = ry + "px";
            }
            raf = requestAnimationFrame(tick);
        };

        const onEnter = () => {
            if (dotRef.current)  dotRef.current.style.transform  = "translate(-50%,-50%) scale(2)";
            if (ringRef.current) ringRef.current.style.opacity = "0";
        };

        const onLeave = () => {
            if (dotRef.current)  dotRef.current.style.transform  = "translate(-50%,-50%) scale(1)";
            if (ringRef.current) ringRef.current.style.opacity = "1";
        };

        document.addEventListener("mousemove", onMove);
        document.querySelectorAll("button, a, input, [role=button]").forEach(el => {
            el.addEventListener("mouseenter", onEnter);
            el.addEventListener("mouseleave", onLeave);
        });

        tick();

        return () => {
            cancelAnimationFrame(raf);
            document.removeEventListener("mousemove", onMove);
        };
    }, []);

    return (
        <>
            <div ref={dotRef}  className="cursor-dot" />
            <div ref={ringRef} className="cursor-ring" />
        </>
    );
}
