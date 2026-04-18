"use client";

import { useCallback, useState, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import { motion } from "framer-motion";
import {
  Upload,
  FileText,
  X,
  Zap,
  Clock,
  CheckCircle2,
  AlertCircle,
  User,
  Tag,
} from "lucide-react";
import { useCortexStore } from "@/store/useCortexStore";
import { useUploadAndStream } from "@/hooks/useBackend";
import { useDemoMode } from "@/hooks/useDemoMode";

// ─── Recent Cases Sidebar ───────────────────────────────────────────

function RecentCases() {
  const [sessions, setSessions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const setSessionId = useCortexStore((s) => s.setSessionId);
  const setDebateMessages = useCortexStore((s) => s.setDebateMessages);
  const setPhase = useCortexStore((s) => s.setPhase);

  useEffect(() => {
    fetch("http://localhost:8000/api/v1/sessions/recent")
      .then((res) => res.json())
      .then((data) => {
        setSessions(data.sessions || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch recent sessions:", err);
        setLoading(false);
      });
  }, []);

  const handleSessionClick = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/sessions/${id}`);
      if (!res.ok) throw new Error("Failed to fetch session");
      const sessionData = await res.json();

      setSessionId(sessionData.session_id);
      if (sessionData.messages) {
        setDebateMessages(sessionData.messages);
      }
      setPhase("COURTROOM");
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        Recent Cases
      </h3>
      {loading && <div className="text-xs text-slate-500">Loading cases...</div>}
      {!loading && sessions.length === 0 && (
        <div className="text-xs text-slate-500">No recent cases available.</div>
      )}
      {sessions.map((c) => {
        // Create a short display ID (first 6 chars of UUID for neatness)
        const displayId = c.id.substring(0, 6).toUpperCase();
        // Extract a nicer time if it's an ISO string
        let displayTime = c.time;
        if (displayTime && displayTime.includes("T")) {
            const d = new Date(displayTime);
            displayTime = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + " " + d.toLocaleDateString();
        }

        return (
          <motion.div
            key={c.id}
            onClick={() => handleSessionClick(c.id)}
            whileHover={{ x: 4 }}
            className="cursor-pointer rounded-xl border border-slate-800/60 bg-slate-900/60 p-4 transition-colors hover:border-slate-700/60 hover:bg-slate-800/40"
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-semibold text-slate-300">
                Patient #{displayId}
              </span>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                  c.status === "complete"
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-amber-500/10 text-amber-400"
                }`}
              >
                {c.status === "complete" ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : (
                  <AlertCircle className="h-3 w-3" />
                )}
                {c.status}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-400">{c.diagnosis}</p>
            <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
              {c.confidence > 0 && <span>{c.confidence}% confidence</span>}
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {displayTime}
              </span>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

// ─── Main Dashboard ─────────────────────────────────────────────────

export default function Dashboard() {
  const uploadedFiles = useCortexStore((s) => s.uploadedFiles);
  const setUploadedFiles = useCortexStore((s) => s.setUploadedFiles);
  const patientSummary = useCortexStore((s) => s.patientSummary);
  const setPatientSummary = useCortexStore((s) => s.setPatientSummary);
  const fileLabels = useCortexStore((s) => s.fileLabels);
  const setFileLabels = useCortexStore((s) => s.setFileLabels);
  const demoMode = useCortexStore((s) => s.demoMode);
  const isLoading = useCortexStore((s) => s.isLoading);
  const error = useCortexStore((s) => s.error);
  const setError = useCortexStore((s) => s.setError);
  const { uploadAndStream } = useUploadAndStream();
  const { startDemo } = useDemoMode();

  const onDrop = useCallback(
    (accepted: File[]) => {
      setUploadedFiles([...uploadedFiles, ...accepted]);
    },
    [uploadedFiles, setUploadedFiles]
  );

  const removeFile = (index: number) => {
    setUploadedFiles(uploadedFiles.filter((_, i) => i !== index));
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "image/*": [".png", ".jpg", ".jpeg"],
    },
    maxSize: 20 * 1024 * 1024, // 20MB
  });

  const handleSubmit = async () => {
    if (demoMode) {
      startDemo();
      return;
    }

    if (uploadedFiles.length === 0 && !patientSummary.trim()) {
      setError("Please upload files or enter a patient summary.");
      return;
    }

    await uploadAndStream(
      uploadedFiles,
      patientSummary,
      fileLabels,
      3
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="mx-auto grid max-w-[1400px] gap-6 p-6 lg:grid-cols-[300px_1fr]"
    >
      {/* Left Column: Recent Cases */}
      <aside className="hidden lg:block">
        <RecentCases />
      </aside>

      {/* Right Column: Data Input */}
      <div className="space-y-6">
        {/* Title */}
        <div>
          <h1 className="text-2xl font-bold text-slate-100">
            New Diagnostic Case
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Upload clinical documents and patient data to initiate multi-agent
            diagnostic analysis.
          </p>
        </div>

        {/* Error Banner */}
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
            <button onClick={() => setError(null)} className="ml-auto">
              <X className="h-4 w-4" />
            </button>
          </motion.div>
        )}

        {/* Drop Zone */}
        <div
          {...getRootProps()}
          className={`group relative cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-300 ${
            isDragActive
              ? "border-cyan-400 bg-cyan-400/5 shadow-[0_0_40px_rgba(6,182,212,0.15)]"
              : "border-slate-700/60 bg-slate-900/40 hover:border-slate-600 hover:bg-slate-800/30"
          }`}
        >
          <input {...getInputProps()} />
          <div className="flex flex-col items-center gap-4">
            <div
              className={`rounded-2xl p-4 transition-colors ${
                isDragActive ? "bg-cyan-400/10" : "bg-slate-800/60"
              }`}
            >
              <Upload
                className={`h-10 w-10 transition-colors ${
                  isDragActive ? "text-cyan-400" : "text-slate-500"
                }`}
              />
            </div>
            <div>
              <p className="text-base font-medium text-slate-300">
                {isDragActive
                  ? "Release to upload"
                  : "Drop files here or click to browse"}
              </p>
              <p className="mt-1 text-sm text-slate-500">
                ECG Images, PDF reports, clinical notes — up to 20MB each
              </p>
            </div>
          </div>
        </div>

        {/* Uploaded File Chips */}
        {uploadedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {uploadedFiles.map((file, i) => (
              <motion.div
                key={`${file.name}-${i}`}
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className="flex items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-800/60 px-3 py-2 text-sm"
              >
                <FileText className="h-4 w-4 text-cyan-400" />
                <span className="max-w-[200px] truncate text-slate-300">
                  {file.name}
                </span>
                <span className="text-xs text-slate-500">
                  {(file.size / 1024).toFixed(0)}KB
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(i);
                  }}
                  className="ml-1 rounded p-0.5 text-slate-500 transition-colors hover:bg-slate-700 hover:text-red-400"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            ))}
          </div>
        )}

        {/* File Labels */}
        {uploadedFiles.length > 0 && (
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm font-medium text-slate-400">
              <Tag className="h-4 w-4" />
              File Labels
              <span className="text-xs text-slate-600">(optional)</span>
            </label>
            <input
              type="text"
              value={fileLabels}
              onChange={(e) => setFileLabels(e.target.value)}
              placeholder="CBC Blood Report, Chest X-Ray, ECG Report"
              className="w-full rounded-xl border border-slate-700/50 bg-slate-900/60 px-4 py-3 text-sm text-slate-200 placeholder-slate-600 transition-colors focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/20"
            />
          </div>
        )}

        {/* Patient Summary */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-slate-400">
            <User className="h-4 w-4" />
            Patient Summary
          </label>
          <textarea
            value={patientSummary}
            onChange={(e) => setPatientSummary(e.target.value)}
            rows={5}
            placeholder="58-year-old male presenting with acute chest pain radiating to left arm, onset 2 hours ago. History of hypertension, type 2 diabetes. Current medications: metformin 500mg, lisinopril 10mg, aspirin 81mg..."
            className="w-full resize-none rounded-xl border border-slate-700/50 bg-slate-900/60 px-4 py-3 text-sm text-slate-200 placeholder-slate-600 transition-colors focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/20"
          />
        </div>

        {/* Submit Button */}
        <motion.button
          onClick={handleSubmit}
          disabled={isLoading}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          className={`relative w-full overflow-hidden rounded-xl px-6 py-4 text-base font-semibold text-white transition-all ${
            isLoading
              ? "cursor-not-allowed bg-slate-700"
              : "bg-gradient-to-r from-cyan-600 to-cyan-500 shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/30"
          }`}
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Analyzing...
            </span>
          ) : (
            <span className="flex items-center justify-center gap-2">
              <Zap className="h-5 w-5" />
              Start Diagnosis
              {demoMode && (
                <span className="rounded-full bg-white/10 px-2 py-0.5 text-xs">
                  DEMO
                </span>
              )}
            </span>
          )}
          {/* Shimmer effect */}
          {!isLoading && (
            <div className="absolute inset-0 -translate-x-full animate-[shimmer_3s_infinite] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
          )}
        </motion.button>
      </div>
    </motion.div>
  );
}
