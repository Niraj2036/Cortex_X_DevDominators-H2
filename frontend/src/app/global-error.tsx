"use client";

// Force dynamic to avoid static generation — works around Next.js 16 prerender bug
// where internal components try to access context that is null during static export.
export const dynamic = "force-dynamic";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body style={{ backgroundColor: "#020617", color: "#e2e8f0", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center" }}>
          <h2 style={{ fontSize: "1.5rem", fontWeight: "bold", marginBottom: "1rem" }}>Something went wrong</h2>
          <p style={{ color: "#94a3b8", marginBottom: "1.5rem" }}>{error.message}</p>
          <button
            onClick={reset}
            style={{
              backgroundColor: "#0891b2",
              color: "white",
              padding: "0.75rem 1.5rem",
              borderRadius: "0.75rem",
              border: "none",
              cursor: "pointer",
              fontSize: "1rem",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
