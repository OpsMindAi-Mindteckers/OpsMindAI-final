"use client";

import { useEffect } from "react";
import { useClerk } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Cpu } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/**
 * Handles the OAuth redirect from Clerk (GitHub / Google).
 *
 * Flow:
 *  1. Clerk redirects back here after the provider grants access.
 *  2. We call handleRedirectCallback() so Clerk finalises the session.
 *  3. We grab the session token from the active Clerk session.
 *  4. We POST it to our backend /auth/set-cookie to create an app session.
 *  5. We persist the token + profile in localStorage and navigate to /dashboard.
 */
export default function SSOCallbackPage() {
    const { handleRedirectCallback, session } = useClerk();
    const router = useRouter();

    useEffect(() => {
        async function finish() {
            try {
                // 1. Let Clerk process the OAuth callback params in the URL
                await handleRedirectCallback({});
            } catch {
                // If the callback was already handled (e.g., page re-render), ignore
            }
        }
        finish();
    }, [handleRedirectCallback]);

    // 2. Once Clerk has an active session, exchange it for our backend token
    useEffect(() => {
        if (!session) return;

        async function exchange() {
            try {
                // Get the short-lived JWT from Clerk
                const token = await session!.getToken();
                if (!token) { router.push("/login"); return; }

                // Tell our backend to set the auth cookie
                const res = await fetch(`${API_BASE}/auth/set-cookie`, {
                    method:      "POST",
                    credentials: "include",
                    headers: {
                        "Authorization": `Bearer ${token}`,
                        "Content-Type":  "application/json",
                    },
                });

                // Store token and profile for frontend components
                localStorage.setItem("auth_token", token);

                const user = session!.user;
                const profile = {
                    name:  user?.fullName ?? user?.primaryEmailAddress?.emailAddress?.split("@")[0] ?? "User",
                    email: user?.primaryEmailAddress?.emailAddress ?? "",
                    role:  "DevOps Engineer",
                };
                localStorage.setItem("opsmind_profile", JSON.stringify(profile));
                window.dispatchEvent(new Event("opsmind_profile_update"));

                if (!res.ok) {
                    // Backend could not set cookie — still redirect (frontend token is enough)
                    console.warn("[sso-callback] backend set-cookie failed:", res.status);
                }
            } catch (err) {
                console.error("[sso-callback] exchange error:", err);
            } finally {
                router.push("/dashboard");
            }
        }

        exchange();
    }, [session, router]);

    return (
        <div className="flex min-h-screen items-center justify-center">
            <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center gap-4"
            >
                <div className="relative">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500 to-violet-500 flex items-center justify-center">
                        <Cpu className="w-8 h-8 text-white" />
                    </div>
                    <div className="absolute inset-0 w-16 h-16 rounded-2xl bg-gradient-to-br from-cyan-500 to-violet-500 blur-xl opacity-50 animate-pulse" />
                </div>
                <div className="text-center space-y-1">
                    <p className="text-white font-semibold">Signing you in…</p>
                    <p className="text-muted-foreground text-sm">Setting up your session</p>
                </div>
                <div className="flex gap-1">
                    {[0, 1, 2].map(i => (
                        <motion.div
                            key={i}
                            className="w-2 h-2 rounded-full bg-cyan-400"
                            animate={{ opacity: [0.3, 1, 0.3] }}
                            transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
                        />
                    ))}
                </div>
            </motion.div>
        </div>
    );
}
