import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Geist_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Omni_CortexX — Command Center",
  description:
    "Multi-agent AI diagnostic system powered by adversarial debate. Upload clinical data and watch AI agents collaborate to reach a medical diagnosis.",
  keywords: [
    "medical AI",
    "diagnostic",
    "multi-agent",
    "clinical decision support",
    "EHR",
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full bg-slate-950 text-slate-200">
        {children}
      </body>
    </html>
  );
}
