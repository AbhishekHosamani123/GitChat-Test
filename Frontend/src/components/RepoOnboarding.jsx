import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowRight,
  Loader2,
  Github,
  AlertCircle,
  Sparkles,
  ShieldCheck,
  SearchCode,
} from 'lucide-react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export default function RepoOnboarding({ onReady }) {
  const [url, setUrl] = useState('');
  const [status, setStatus] = useState('idle');
  const [repoInfo, setRepoInfo] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url) return;

    setStatus('submitting');
    setErrorMsg('');

    try {
      const res = await fetch(`${API_BASE}/repos/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: url }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Failed to ingest repository');
      }

      setRepoInfo(data);
      setStatus('polling');
    } catch (err) {
      console.error(err);
      setErrorMsg(err.message);
      setStatus('error');
    }
  };

  useEffect(() => {
    let interval;
    if (status === 'polling' && repoInfo?.repo_id) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/repos/${repoInfo.repo_id}/status`);
          const data = await res.json();

          if (!res.ok) throw new Error(data.detail);

          setRepoInfo(data);

          if (data.status === 'completed') {
            clearInterval(interval);
            setTimeout(() => {
              onReady(data);
            }, 1000);
          }
        } catch (err) {
          console.error(err);
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [status, repoInfo, onReady]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      className="w-full max-w-4xl py-6"
    >
      <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl backdrop-blur-2xl sm:p-8">
        <div className="pointer-events-none absolute right-0 top-0 h-48 w-48 rounded-full bg-primary/20 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 left-0 h-48 w-48 rounded-full bg-emerald-500/10 blur-3xl" />

        <div className="relative z-10 grid gap-8 lg:grid-cols-[1.1fr_1fr] lg:gap-10">
          <div>
            <motion.div
              initial={{ scale: 0.85, opacity: 0.8 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: 'spring', bounce: 0.35 }}
              className="mb-5 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary-light"
            >
              <Sparkles className="h-3.5 w-3.5" />
              Instant Repository Intelligence
            </motion.div>

            <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
              Turn any GitHub repo into a smart chatbot
            </h2>
            <p className="mt-3 max-w-lg text-sm leading-relaxed text-white/65 sm:text-base">
              Paste a public repository URL. GitChat parses and indexes the codebase so you can ask architecture, logic,
              and implementation questions in plain English.
            </p>

            <div className="mt-7 grid gap-3 text-sm text-white/70 sm:grid-cols-3 lg:grid-cols-1">
              <div className="feature-chip">
                <SearchCode className="h-4 w-4 text-primary-light" />
                <span>Code-aware retrieval</span>
              </div>
              <div className="feature-chip">
                <ShieldCheck className="h-4 w-4 text-emerald-300" />
                <span>Per-repo isolated context</span>
              </div>
              <div className="feature-chip">
                <Github className="h-4 w-4 text-white/70" />
                <span>Works with public GitHub URLs</span>
              </div>
            </div>
          </div>

          <div className="relative rounded-2xl border border-white/10 bg-black/25 p-5 sm:p-6">
            <motion.div
              initial={{ scale: 0.8 }}
              animate={{ scale: 1 }}
              transition={{ type: 'spring', bounce: 0.45 }}
              className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-tr from-primary-dark to-primary-light shadow-lg shadow-primary/25"
            >
              <Github className="h-7 w-7 text-white" />
            </motion.div>

            <h3 className="text-center text-lg font-semibold">Connect Repository</h3>
            <p className="mb-5 mt-1 text-center text-sm text-white/60">Enter your repository URL to begin indexing.</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="group relative">
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  disabled={status === 'submitting' || status === 'polling'}
                  placeholder="https://github.com/owner/repo"
                  className="w-full rounded-xl border border-white/15 bg-black/40 px-4 py-3.5 pl-11 text-white placeholder-white/35 outline-none transition-all focus:border-primary/60 focus:ring-2 focus:ring-primary/30 disabled:cursor-not-allowed disabled:opacity-50"
                />
                <Github className="absolute left-3.5 top-1/2 h-4.5 w-4.5 -translate-y-1/2 text-white/40 transition-colors group-focus-within:text-primary-light" />
              </div>

              {status === 'error' && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className="flex items-start gap-2 rounded-lg border border-red-400/25 bg-red-400/10 p-3 text-sm text-red-300"
                >
                  <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                  <span>{errorMsg}</span>
                </motion.div>
              )}

              <button
                type="submit"
                disabled={!url || status !== 'idle'}
                className="group inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary-dark px-4 py-3.5 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {status === 'idle' || status === 'error' ? (
                  <>
                    Start Indexing
                    <ArrowRight className="h-4.5 w-4.5 transition-transform group-hover:translate-x-0.5" />
                  </>
                ) : status === 'polling' ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4.5 w-4.5 animate-spin" />
                    {repoInfo?.status === 'completed' ? 'Ready!' : 'Processing Codebase...'}
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4.5 w-4.5 animate-spin" />
                    Initializing...
                  </span>
                )}
              </button>
            </form>

            <AnimatePresence>
              {status === 'polling' && repoInfo && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-5 space-y-4 border-t border-white/10 pt-4"
                >
                  <div className="flex items-center justify-between text-xs sm:text-sm">
                    <span className="text-white/60">Indexing status</span>
                    <span className="font-medium capitalize text-primary-light">{repoInfo.status}</span>
                  </div>

                  <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
                    {repoInfo.status === 'completed' ? (
                      <motion.div initial={{ width: 0 }} animate={{ width: '100%' }} className="h-full bg-emerald-400" />
                    ) : (
                      <motion.div
                        className="relative h-full rounded-full bg-primary"
                        initial={{ width: '0%' }}
                        animate={{
                          width:
                            repoInfo.chunks_total > 0
                              ? `${(repoInfo.chunks_indexed / repoInfo.chunks_total) * 100}%`
                              : '10%',
                        }}
                      >
                        <div className="absolute inset-0 animate-pulse bg-white/20" />
                      </motion.div>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-center text-xs text-white/60">
                    <div className="rounded-lg border border-white/10 bg-white/5 p-2.5">
                      <div className="text-sm font-semibold text-white">{repoInfo.files_processed || 0}</div>
                      <div>Files parsed</div>
                    </div>
                    <div className="rounded-lg border border-white/10 bg-white/5 p-2.5">
                      <div className="text-sm font-semibold text-white">
                        {repoInfo.chunks_indexed || 0} / {repoInfo.chunks_total || 0}
                      </div>
                      <div>Chunks indexed</div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
