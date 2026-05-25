"use client";

import { useClerk } from "@clerk/nextjs";

type OAuthProvider = "oauth_github" | "oauth_google";

export function useOAuth() {
    const clerk = useClerk();

    async function startOAuth(provider: OAuthProvider): Promise<void> {
        const signIn = clerk.client?.signIn;
        if (!signIn) throw new Error("Clerk client not ready");
        await signIn.authenticateWithRedirect({
            strategy:            provider,
            redirectUrl:         "/sso-callback",
            redirectUrlComplete: "/sso-callback",
        });
    }

    return { startOAuth };
}
