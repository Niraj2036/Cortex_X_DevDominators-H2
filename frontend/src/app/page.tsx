"use client";

import dynamic from "next/dynamic";

// Load the entire phase-router client-side only — framer-motion's
// AnimatePresence breaks Next.js 16's static prerendering of error pages.
const AppShell = dynamic(() => import("../components/AppShell"), { ssr: false });

export default function Home() {
  return <AppShell />;
}

