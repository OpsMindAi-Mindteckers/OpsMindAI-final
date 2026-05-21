import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "OpsMind AI — Intelligent DevOps Platform",
  description:
    "AI-powered DevOps platform with SRE, Code Refactor, and Testing agents for autonomous incident resolution and deployment management.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} dark h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-[#030712]">{children}</body>
    </html>
  );
}
