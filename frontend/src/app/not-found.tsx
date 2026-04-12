export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-200">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-cyan-400 mb-4">404</h1>
        <h2 className="text-xl font-semibold mb-2">Page Not Found</h2>
        <p className="text-slate-400 mb-6">
          The diagnostic case you&apos;re looking for doesn&apos;t exist.
        </p>
        <a
          href="/"
          className="rounded-xl bg-cyan-600 px-6 py-3 text-white hover:bg-cyan-500 inline-block"
        >
          Return to Command Center
        </a>
      </div>
    </div>
  );
}
