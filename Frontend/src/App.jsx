import React, { useState } from 'react';
import RepoOnboarding from './components/RepoOnboarding';
import ChatInterface from './components/ChatInterface';
import { AnimatePresence } from 'framer-motion';
import { Github } from 'lucide-react';

function App() {
  const [repoData, setRepoData] = useState(null);

  const handleRepoReady = (data) => {
    setRepoData(data);
  };

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-background text-white selection:bg-primary/30">
      <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden">
        <div className="absolute -top-[30%] -left-[10%] h-[42rem] w-[42rem] rounded-full bg-primary/15 blur-[120px]" />
        <div className="absolute top-[35%] -right-[15%] h-[38rem] w-[38rem] rounded-full bg-emerald-500/10 blur-[120px]" />
        <div className="absolute left-1/2 top-1/2 h-[30rem] w-[30rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyan-400/5 blur-[100px]" />
      </div>

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 pb-6 pt-5 sm:px-6 lg:px-10">
        <header className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3 backdrop-blur-xl sm:px-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary-dark shadow-lg shadow-primary/30">
              <Github className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-semibold tracking-tight sm:text-lg">GitChat</h1>
              <p className="text-xs text-white/60">Chat with any public GitHub repository</p>
            </div>
          </div>
          <span className="rounded-full border border-emerald-300/20 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-300">
            AI Repo Assistant
          </span>
        </header>

        <main className="mt-4 flex flex-1 items-stretch justify-center overflow-hidden">
          <AnimatePresence mode="wait">
            {!repoData ? (
              <RepoOnboarding key="onboarding" onReady={handleRepoReady} />
            ) : (
              <ChatInterface key="chat" repoData={repoData} onReset={() => setRepoData(null)} />
            )}
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}

export default App;
