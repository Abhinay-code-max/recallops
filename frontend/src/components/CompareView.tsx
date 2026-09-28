import React, { useState, useEffect } from 'react';
import {
  GitCompare,
  Sparkles,
  Bot,
  Brain,
  ShieldCheck,
  AlertTriangle,
  Zap,
  BookOpen,
  ArrowRight,
  RefreshCw,
} from 'lucide-react';
import { Alert, CompareResponse, DemoAlertOut } from '../types';
import { api } from '../services/api';

export const CompareView: React.FC = () => {
  const [demoAlerts, setDemoAlerts] = useState<DemoAlertOut[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getDemoAlerts()
      .then((demos) => {
        setDemoAlerts(demos);
        if (demos.length > 0) {
          setSelectedAlert(demos[0].alert);
          runComparison(demos[0].alert);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  const runComparison = async (alertToCompare: Alert) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.compare({ alert: alertToCompare });
      setCompareResult(res);
    } catch (err: any) {
      setError(err.message || 'Comparison failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectDemo = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const found = demoAlerts.find((d) => d.alert_id === e.target.value);
    if (found) {
      setSelectedAlert(found.alert);
      runComparison(found.alert);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <GitCompare className="w-6 h-6 text-brand-500" />
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
              Memory Comparison Studio
            </h1>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 font-medium">
            Side-by-side verification: Standard Stateless LLM vs Hindsight-Augmented RecallOps
          </p>
        </div>

        {/* Preset Selector */}
        {demoAlerts.length > 0 && (
          <div className="flex items-center space-x-2">
            <label className="text-xs font-bold text-slate-600 dark:text-slate-400">
              Demo Alert:
            </label>
            <select
              onChange={handleSelectDemo}
              className="px-3 py-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white font-semibold focus:outline-none focus:ring-2 focus:ring-brand-500 cursor-pointer shadow-xs"
            >
              {demoAlerts.map((d) => (
                <option key={d.alert_id} value={d.alert_id}>
                  [{d.alert.severity}] {d.title}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && (
        <div className="p-4 bg-rose-50 dark:bg-rose-950/80 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 rounded-2xl text-xs">
          {error}
        </div>
      )}

      {selectedAlert && (
        <div className="p-4 bg-white dark:bg-[#161F36] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center space-x-3">
            <span className="px-2 py-0.5 rounded font-bold bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800">
              {selectedAlert.severity}
            </span>
            <span className="font-extrabold text-slate-900 dark:text-white">
              {selectedAlert.title}
            </span>
            <span className="text-slate-400 font-mono">• {selectedAlert.service}</span>
          </div>

          <button
            onClick={() => selectedAlert && runComparison(selectedAlert)}
            disabled={isLoading}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl font-bold transition-all disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span>Re-run Comparison</span>
          </button>
        </div>
      )}

      {/* Side-by-Side Comparison Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: WITHOUT MEMORY */}
        <div className="bg-white dark:bg-[#161F36] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden flex flex-col">
          <div className="p-4 bg-slate-100 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Bot className="w-4 h-4 text-slate-500" />
              <h3 className="font-extrabold text-sm text-slate-800 dark:text-slate-200">
                Stateless LLM (Zero Memory)
              </h3>
            </div>
            <span className="text-[10px] font-mono font-bold bg-slate-200 dark:bg-slate-700 px-2 py-0.5 rounded text-slate-600 dark:text-slate-300">
              Generic Advice
            </span>
          </div>

          <div className="p-5 flex-1 space-y-4">
            <div className="text-[11px] text-slate-500 italic">
              Prompted with alert details only. Has zero knowledge of team history, prior outages, or what mitigations previously failed.
            </div>

            {isLoading ? (
              <div className="py-16 text-center text-xs text-slate-400">
                Generating stateless baseline...
              </div>
            ) : compareResult?.without_memory ? (
              <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs text-slate-800 dark:text-slate-300 whitespace-pre-wrap leading-relaxed font-sans">
                {compareResult.without_memory.text}
              </div>
            ) : (
              <div className="text-xs text-slate-400 py-10 text-center">No comparison run yet.</div>
            )}
          </div>
        </div>

        {/* Right Column: WITH RECALLOPS MEMORY */}
        <div className="bg-white dark:bg-[#161F36] rounded-2xl border-2 border-brand-500/50 dark:border-brand-500/60 shadow-lg overflow-hidden flex flex-col">
          <div className="p-4 bg-brand-50 dark:bg-brand-950/80 border-b border-brand-200 dark:border-brand-900 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Brain className="w-4 h-4 text-brand-600 dark:text-brand-400" />
              <h3 className="font-extrabold text-sm text-brand-900 dark:text-brand-200">
                RecallOps (Hindsight Memory Active)
              </h3>
            </div>
            <span className="text-[10px] font-mono font-extrabold bg-brand-600 text-white px-2 py-0.5 rounded shadow-xs">
              Grounded & Outcome-Ranked
            </span>
          </div>

          <div className="p-5 flex-1 space-y-4">
            <div className="text-[11px] text-brand-700 dark:text-brand-300 font-semibold">
              Grounds directly in recalled outages. Cites past incident IDs, gives outcome-ranked fixes, and warns of failed mitigations.
            </div>

            {isLoading ? (
              <div className="py-16 text-center text-xs text-brand-600 dark:text-brand-400 animate-pulse font-semibold">
                Recalling from Hindsight memory & scoring fixes...
              </div>
            ) : compareResult?.with_memory ? (
              <div className="space-y-4 text-xs">
                {/* Warnings */}
                {compareResult.with_memory.warnings?.map((w, idx) => (
                  <div key={idx} className="p-3 bg-rose-50 dark:bg-rose-950/70 border border-rose-300 dark:border-rose-800 rounded-xl text-rose-700 dark:text-rose-300">
                    <strong className="block font-bold">WARNING: {w.kind}</strong>
                    <span>{w.message}</span>
                  </div>
                ))}

                {/* Briefing Sections */}
                <div className="p-4 bg-slate-50 dark:bg-slate-900/90 rounded-xl border border-slate-200 dark:border-slate-800 space-y-3">
                  <div>
                    <span className="font-bold text-[10px] uppercase text-slate-400 block mb-0.5">Root Cause:</span>
                    <p className="text-slate-800 dark:text-slate-200 font-medium">{compareResult.with_memory.sections.root_cause}</p>
                  </div>

                  <div>
                    <span className="font-bold text-[10px] uppercase text-slate-400 block mb-0.5">First Action (Top Ranked):</span>
                    <p className="text-emerald-700 dark:text-emerald-300 font-bold">{compareResult.with_memory.sections.first_actions[0]}</p>
                  </div>

                  {compareResult.with_memory.sections.last_fixed_by && (
                    <div className="font-mono text-[11px] text-slate-500">
                      Resolved previously by: <strong className="text-slate-700 dark:text-slate-300 font-sans">{compareResult.with_memory.sections.last_fixed_by}</strong>
                    </div>
                  )}
                </div>

                {/* Ranked Fixes Summary */}
                <div>
                  <h4 className="font-bold text-xs text-slate-900 dark:text-white mb-2">
                    Ranked Mitigations ({compareResult.with_memory.ranked_fixes.length}):
                  </h4>
                  <div className="space-y-2">
                    {compareResult.with_memory.ranked_fixes.map((fix) => (
                      <div key={fix.rank} className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          <span className="w-5 h-5 rounded-full bg-brand-600 text-white text-[10px] font-bold flex items-center justify-center">
                            #{fix.rank}
                          </span>
                          <span className="font-bold text-slate-800 dark:text-slate-200">{fix.label}</span>
                        </div>
                        <span className="font-mono text-emerald-600 dark:text-emerald-400 font-bold">
                          Score: {fix.score.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Evidence citations */}
                {compareResult.with_memory.evidence?.length > 0 && (
                  <div className="p-3 bg-brand-50/50 dark:bg-brand-950/40 rounded-xl border border-brand-200 dark:border-brand-900 font-mono text-[11px] text-brand-700 dark:text-brand-300">
                    Recalled Citations: {compareResult.with_memory.evidence.map((e) => e.incident_id).join(', ')}
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CompareView;
