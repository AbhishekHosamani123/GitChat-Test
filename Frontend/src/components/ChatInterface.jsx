import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Send, Bot, User, Github, Loader2, ArrowLeft, Code, Sparkles } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export default function ChatInterface({ repoData, onReset }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'assistant',
      content: `Hello! I'm ready to answer questions about ${repoData?.name || 'this repository'} (${repoData?.repo_summary || 'No summary available'}). What would you like to know?`,
    },
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isTyping) return;

    const userMsg = { id: Date.now(), role: 'user', content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsTyping(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_id: repoData.repo_id,
          question: userMsg.content,
        }),
      });

      const data = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: data.answer,
          sources: data.sources,
          confidence: data.confidence,
        },
      ]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: 'I encountered an error trying to process your request. Ensure the backend server is running.',
        },
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      className="flex h-[calc(100vh-7.5rem)] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] shadow-2xl backdrop-blur-2xl"
    >
      <div className="flex items-center justify-between border-b border-white/10 bg-black/20 px-4 py-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <button
            onClick={onReset}
            className="rounded-lg border border-white/10 bg-white/5 p-2 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
            aria-label="Back to repository input"
          >
            <ArrowLeft className="h-4.5 w-4.5" />
          </button>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold sm:text-base">
              <span className="inline-flex items-center gap-1.5">
                <Github className="h-4 w-4 text-white/70" />
                {repoData?.owner}/{repoData?.name}
              </span>
            </h2>
            <div className="mt-0.5 inline-flex items-center gap-1.5 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-300">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-300" />
              Indexed and ready
            </div>
          </div>
        </div>
        <div className="hidden items-center gap-1 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-1 text-xs text-primary-light sm:flex">
          <Sparkles className="h-3.5 w-3.5" />
          Repo AI
        </div>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
        {messages.map((msg) => (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            key={msg.id}
            className={`flex max-w-[92%] gap-3 sm:max-w-[82%] ${msg.role === 'user' ? 'ml-auto flex-row-reverse' : ''}`}
          >
            <div
              className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${
                msg.role === 'user'
                  ? 'bg-gradient-to-br from-primary to-primary-dark text-white'
                  : 'border border-white/10 bg-white/8 text-primary-light'
              }`}
            >
              {msg.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
            </div>

            <div className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div
                className={`rounded-2xl p-3.5 sm:p-4 ${
                  msg.role === 'user'
                    ? 'rounded-tr-sm bg-gradient-to-br from-primary to-primary-dark text-white shadow-md shadow-primary/20'
                    : 'rounded-tl-sm border border-white/10 bg-black/25 text-white/90'
                }`}
              >
                {msg.role === 'assistant' ? (
                  <div className="prose prose-invert max-w-none prose-p:my-2 prose-p:leading-relaxed prose-pre:my-2 prose-pre:border prose-pre:border-white/10 prose-pre:bg-black/50 prose-code:text-primary-light">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                )}

                {msg.role === 'assistant' && msg.confidence !== undefined && (
                  <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/60">
                    <span>Confidence</span>
                    <span
                      className={`font-semibold ${
                        msg.confidence > 0.7
                          ? 'text-emerald-300'
                          : msg.confidence > 0.4
                            ? 'text-yellow-300'
                            : 'text-red-300'
                      }`}
                    >
                      {Math.round(msg.confidence * 100)}%
                    </span>
                  </div>
                )}
              </div>

              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-2 flex w-full flex-wrap gap-2">
                  {msg.sources.map((src, idx) => (
                    <div
                      key={idx}
                      className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-black/35 px-2 py-1 text-[11px] text-white/65"
                    >
                      <Code className="h-3 w-3 text-primary-light/80" />
                      <span className="font-mono">{src.file_path || src.file || 'unknown-file'}</span>
                      {src.start_line && src.end_line && (
                        <span className="text-white/45">
                          L{src.start_line}-{src.end_line}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        ))}

        {isTyping && (
          <div className="flex max-w-[85%] gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-white/8 text-primary-light">
              <Bot className="h-4 w-4" />
            </div>
            <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm border border-white/10 bg-black/25 p-3.5 text-sm text-white/60">
              <Loader2 className="h-4 w-4 animate-spin" />
              Reading codebase...
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-white/10 bg-black/20 p-3 sm:p-4">
        <form onSubmit={handleSubmit} className="relative mx-auto flex max-w-5xl items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about this codebase..."
            className="w-full rounded-xl border border-white/15 bg-black/35 px-4 py-3 pr-12 text-sm text-white placeholder-white/40 outline-none transition-all focus:border-primary/60 focus:ring-2 focus:ring-primary/30 sm:text-base"
            disabled={isTyping}
          />
          <button
            type="submit"
            disabled={!input.trim() || isTyping}
            className="absolute right-1.5 rounded-lg bg-gradient-to-r from-primary to-primary-dark p-2 text-white transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Send question"
          >
            <Send className="h-4.5 w-4.5" />
          </button>
        </form>
      </div>
    </motion.div>
  );
}
