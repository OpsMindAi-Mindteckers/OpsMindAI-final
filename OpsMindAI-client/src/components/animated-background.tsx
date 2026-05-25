"use client";

import { useEffect, useRef } from "react";

interface Particle {
    x: number; y: number;
    vx: number; vy: number;
    size: number; opacity: number;
    hue: number; life: number; maxLife: number;
    type: "dot" | "orb" | "trail";
    trail: { x: number; y: number }[];
}

interface EnergyOrb {
    x: number; y: number;
    radius: number; hue: number;
    pulse: number; pulseSpeed: number;
    opacity: number;
}

interface DataStream {
    x: number; y: number;
    speed: number; length: number;
    opacity: number; hue: number;
    chars: string[];
}

export function AnimatedBackground() {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const mouseRef  = useRef({ x: 0, y: 0 });

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        let raf: number;
        let t = 0;
        let particles:   Particle[]   = [];
        let energyOrbs:  EnergyOrb[]  = [];
        let dataStreams:  DataStream[] = [];

        const HEX_CHARS = "01アイウエオカキクケコ∞Σ∆Ω█▓▒░⬡⬢◈◉";

        const resize = () => {
            canvas.width  = window.innerWidth;
            canvas.height = window.innerHeight;
            init();
        };

        const mkParticle = (): Particle => ({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            vx: (Math.random() - 0.5) * 0.4,
            vy: (Math.random() - 0.5) * 0.4,
            size: Math.random() * 2.5 + 0.3,
            opacity: Math.random() * 0.6 + 0.1,
            hue: [187, 270, 300, 160][Math.floor(Math.random() * 4)],
            life: 0, maxLife: 200 + Math.random() * 400,
            type: Math.random() > 0.85 ? "orb" : Math.random() > 0.7 ? "trail" : "dot",
            trail: [],
        });

        const mkOrb = (): EnergyOrb => ({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            radius: 80 + Math.random() * 200,
            hue: [187, 270, 300][Math.floor(Math.random() * 3)],
            pulse: Math.random() * Math.PI * 2,
            pulseSpeed: 0.005 + Math.random() * 0.01,
            opacity: 0.03 + Math.random() * 0.05,
        });

        const mkStream = (): DataStream => ({
            x: Math.random() * canvas.width,
            y: -50,
            speed: 0.5 + Math.random() * 1.5,
            length: 8 + Math.floor(Math.random() * 15),
            opacity: 0.1 + Math.random() * 0.2,
            hue: Math.random() > 0.5 ? 187 : 270,
            chars: Array.from({ length: 20 }, () => HEX_CHARS[Math.floor(Math.random() * HEX_CHARS.length)]),
        });

        const init = () => {
            const density = (canvas.width * canvas.height) / 12000;
            particles  = Array.from({ length: Math.min(Math.floor(density), 120) }, mkParticle);
            energyOrbs = Array.from({ length: 6 }, mkOrb);
            dataStreams = Array.from({ length: 12 }, mkStream);
        };

        const drawEnergyOrbs = () => {
            energyOrbs.forEach(orb => {
                orb.pulse += orb.pulseSpeed;
                const r = orb.radius * (1 + Math.sin(orb.pulse) * 0.15);
                const grad = ctx.createRadialGradient(orb.x, orb.y, 0, orb.x, orb.y, r);
                grad.addColorStop(0, `hsla(${orb.hue}, 90%, 60%, ${orb.opacity * 2})`);
                grad.addColorStop(0.4, `hsla(${orb.hue}, 80%, 50%, ${orb.opacity})`);
                grad.addColorStop(1, "transparent");
                ctx.fillStyle = grad;
                ctx.beginPath();
                ctx.arc(orb.x, orb.y, r, 0, Math.PI * 2);
                ctx.fill();

                // Slow drift
                orb.x += Math.sin(orb.pulse * 0.3) * 0.3;
                orb.y += Math.cos(orb.pulse * 0.2) * 0.2;
                if (orb.x < -200) orb.x = canvas.width + 100;
                if (orb.x > canvas.width + 200) orb.x = -100;
                if (orb.y < -200) orb.y = canvas.height + 100;
                if (orb.y > canvas.height + 200) orb.y = -100;
            });
        };

        const drawGrid = () => {
            const size = 60;
            const offset = (t * 0.3) % size;
            ctx.strokeStyle = "rgba(6,182,212,0.025)";
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            for (let x = -size + offset; x < canvas.width + size; x += size) {
                ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height);
            }
            for (let y = -size + offset; y < canvas.height + size; y += size) {
                ctx.moveTo(0, y); ctx.lineTo(canvas.width, y);
            }
            ctx.stroke();
        };

        const drawDataStreams = () => {
            ctx.font = "10px monospace";
            dataStreams.forEach(ds => {
                ds.y += ds.speed;
                for (let i = 0; i < ds.length; i++) {
                    const alpha = (1 - i / ds.length) * ds.opacity * (i === 0 ? 1.5 : 1);
                    ctx.fillStyle = `hsla(${ds.hue}, 90%, 65%, ${alpha})`;
                    const char = ds.chars[(Math.floor(t * 0.05) + i) % ds.chars.length];
                    ctx.fillText(char, ds.x, ds.y - i * 14);
                }
                if (ds.y > canvas.height + ds.length * 14) {
                    ds.y = -50;
                    ds.x = Math.random() * canvas.width;
                }
            });
        };

        const drawParticles = () => {
            const mx = mouseRef.current.x;
            const my = mouseRef.current.y;

            particles.forEach((p, idx) => {
                // Mouse repulsion
                const dx = p.x - mx;
                const dy = p.y - my;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 100 && dist > 0) {
                    const force = (100 - dist) / 100 * 0.3;
                    p.vx += (dx / dist) * force;
                    p.vy += (dy / dist) * force;
                }

                // Damping
                p.vx *= 0.99;
                p.vy *= 0.99;
                p.x += p.vx;
                p.y += p.vy;
                p.life++;

                if (p.x < 0) p.x = canvas.width;
                if (p.x > canvas.width) p.x = 0;
                if (p.y < 0) p.y = canvas.height;
                if (p.y > canvas.height) p.y = 0;

                const lifeRatio = p.life / p.maxLife;
                const fade = lifeRatio < 0.1 ? lifeRatio * 10 : lifeRatio > 0.9 ? (1 - lifeRatio) * 10 : 1;
                const alpha = p.opacity * fade;

                if (p.type === "orb") {
                    const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 4);
                    grad.addColorStop(0, `hsla(${p.hue}, 90%, 70%, ${alpha})`);
                    grad.addColorStop(1, "transparent");
                    ctx.fillStyle = grad;
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.size * 4, 0, Math.PI * 2);
                    ctx.fill();
                } else if (p.type === "trail") {
                    p.trail.push({ x: p.x, y: p.y });
                    if (p.trail.length > 12) p.trail.shift();
                    if (p.trail.length > 1) {
                        for (let i = 1; i < p.trail.length; i++) {
                            const ta = (i / p.trail.length) * alpha * 0.5;
                            ctx.strokeStyle = `hsla(${p.hue}, 90%, 65%, ${ta})`;
                            ctx.lineWidth = p.size * (i / p.trail.length);
                            ctx.beginPath();
                            ctx.moveTo(p.trail[i-1].x, p.trail[i-1].y);
                            ctx.lineTo(p.trail[i].x, p.trail[i].y);
                            ctx.stroke();
                        }
                    }
                } else {
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
                    ctx.fillStyle = `hsla(${p.hue}, 85%, 65%, ${alpha})`;
                    ctx.fill();
                }

                if (p.life >= p.maxLife) particles[idx] = mkParticle();
            });
        };

        const drawConnections = () => {
            for (let i = 0; i < particles.length; i++) {
                for (let j = i + 1; j < particles.length; j++) {
                    const dx = particles[i].x - particles[j].x;
                    const dy = particles[i].y - particles[j].y;
                    const d  = Math.sqrt(dx * dx + dy * dy);
                    if (d < 100) {
                        const alpha = (1 - d / 100) * 0.08;
                        const hue = (particles[i].hue + particles[j].hue) / 2;
                        ctx.beginPath();
                        ctx.strokeStyle = `hsla(${hue}, 80%, 60%, ${alpha})`;
                        ctx.lineWidth = 0.5;
                        ctx.moveTo(particles[i].x, particles[i].y);
                        ctx.lineTo(particles[j].x, particles[j].y);
                        ctx.stroke();
                    }
                }
            }
        };

        const drawScanLine = () => {
            const y = ((t * 0.3) % (canvas.height + 60)) - 30;
            const grad = ctx.createLinearGradient(0, y - 20, 0, y + 20);
            grad.addColorStop(0, "transparent");
            grad.addColorStop(0.5, "rgba(6,182,212,0.03)");
            grad.addColorStop(1, "transparent");
            ctx.fillStyle = grad;
            ctx.fillRect(0, y - 20, canvas.width, 40);
        };

        const animate = () => {
            t++;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            // Deep space background
            const bg = ctx.createRadialGradient(
                canvas.width * 0.5, canvas.height * 0.4, 0,
                canvas.width * 0.5, canvas.height * 0.4, canvas.width * 0.8
            );
            bg.addColorStop(0, "rgba(4, 10, 30, 0.2)");
            bg.addColorStop(1, "transparent");
            ctx.fillStyle = bg;
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            drawGrid();
            drawEnergyOrbs();
            drawDataStreams();
            drawConnections();
            drawParticles();
            drawScanLine();

            raf = requestAnimationFrame(animate);
        };

        const onMouse = (e: MouseEvent) => {
            mouseRef.current = { x: e.clientX, y: e.clientY };
        };

        resize();
        animate();

        window.addEventListener("resize",    resize);
        window.addEventListener("mousemove", onMouse);

        return () => {
            cancelAnimationFrame(raf);
            window.removeEventListener("resize",    resize);
            window.removeEventListener("mousemove", onMouse);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            className="fixed inset-0 z-0 pointer-events-none"
            aria-hidden="true"
        />
    );
}
