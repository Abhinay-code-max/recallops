import React, { useState, useEffect } from 'react';
import {
  Lightbulb,
  Sparkles,
  Clock,
  AlertTriangle,
  Users,
  TrendingUp,
  RefreshCw,
  ExternalLink,
  ShieldAlert,
} from 'lucide-react';
import { InsightsResponse } from '../types';
import { api } from '../services/api';

interface InsightsViewProps {
  onSelectIncident?: (incidentId: string) => void;
}

export const InsightsView: React.FC<InsightsViewProps> = ({ onSelectIncident }) => {
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInsights = async () => {
    try {
      const data = await api.getInsights();
      setInsights(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load insights');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchInsights();

    // Poll if reflect is still pending
    const interval = setInterval(() => {
      if (insights?.reflect_status === 'pending') {
        fetchInsights();
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [insights?.reflect_status]);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <Lightbulb className="w-6 h-6 text-amber-500" />
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
              Pattern Insights & Hindsight Reflection
            </h1>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 font-medium">
            Systemic operational patterns, recurrence intervals, open permanent fixes, and team expertise
          </p>
        </div>

        <button
          onClick={fetchInsights}
          disabled={isLoading}
          className="flex items-center space-x-1.5 px-3.5 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-bold transition-all cursor-pointer self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Refresh Insights</span>
        </button>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 dark:bg-rose-950/80 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 rounded-2xl text-xs">
          {error}
        </div>
      )}

      {/* Reflect Narrative Summary Card */}
      <div className="p-6 bg-gradient-to-r from-brand-900/40 via-indigo-950/40 to-slate-900/60 rounded-3xl border border-brand-500/30 shadow-lg space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-brand-400" />
            <h3 className="font-extrabold text-sm text-slate-900 dark:text-white">
              Hindsight Reflect Synthesis
            </h3>
          </div>
          <span
            className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider ${
              insights?.reflect_status === 'ready'
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                : insights?.reflect_status === 'pending'
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40 animate-pulse'
                : 'bg-slate-700 text-slate-300'
            }`}
          >
            Reflect: {insights?.reflect_status || 'Initializing'}
          </span>
        </div>

        {insights?.reflect_summary ? (
          <p className="text-xs text-slate-700 dark:text-slate-200 leading-relaxed font-sans font-medium whitespace-pre-wrap">
            {insights.reflect_summary}
          </p>
        ) : (
          <div className="text-xs text-slate-400 flex items-center space-x-2 py-2">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-brand-400" />
            <span>Reflect engine is analyzing structured memory banks in the background...</span>
          </div>
        )}
      </div>

      {/* 2-Column Insights Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Card 1: Recurring Outage Patterns */}
        <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center space-x-2 border-b border-slate-200 dark:border-slate-800 pb-3">
            <Clock className="w-4 h-4 text-indigo-500" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">
              Recurring Incident Patterns ({insights?.patterns.length || 0})
            </h3>
          </div>

          <div className="space-y-3">
            {insights?.patterns.map((p, i) => (
              <div
                key={i}
                className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-1.5"
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-extrabold text-slate-900 dark:text-white">
                    {p.title}
                  </span>
                  <span className="font-mono text-xs font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-2 py-0.5 rounded">
                    Freq: {p.frequency}x
                  </span>
                </div>
                <div className="text-xs text-slate-500 font-mono flex items-center space-x-3">
                  <span>Service: <strong className="text-slate-700 dark:text-slate-300 font-sans">{p.service}</strong></span>
                  {p.interval_days && (
                    <span>• Avg Interval: ~{Math.round(p.interval_days)} days</span>
                  )}
                </div>
                {p.incident_ids?.length > 0 && (
                  <div className="text-[11px] font-mono text-brand-600 dark:text-brand-400">
                    Incidents: {p.incident_ids.join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Card 2: Open Permanent Fixes (Unfinished Postmortem Work) */}
        <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center space-x-2 border-b border-slate-200 dark:border-slate-800 pb-3">
            <ShieldAlert className="w-4 h-4 text-rose-500" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">
              Open Permanent Fixes ({insights?.open_permanent_fixes.length || 0})
            </h3>
          </div>

          <div className="space-y-3">
            {insights?.open_permanent_fixes.length === 0 ? (
              <div className="text-xs text-slate-400 py-4 text-center">No open permanent fixes flagged.</div>
            ) : (
              insights?.open_permanent_fixes.map((fix, i) => (
                <div
                  key={i}
                  className="p-3.5 rounded-xl bg-rose-50/70 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 space-y-1"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-rose-800 dark:text-rose-200">
                      {fix.title}
                    </span>
                    <span className="font-mono text-[10px] font-bold text-rose-600 dark:text-rose-400 bg-rose-100 dark:bg-rose-950 px-2 py-0.5 rounded">
                      {fix.incident_id}
                    </span>
                  </div>
                  <p className="text-xs text-rose-700 dark:text-rose-300 font-medium">
                    {fix.message}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Card 3: Team Knowledge & Ownership */}
        <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center space-x-2 border-b border-slate-200 dark:border-slate-800 pb-3">
            <Users className="w-4 h-4 text-blue-500" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">
              Team Knowledge & Expertise ({insights?.team_knowledge.length || 0})
            </h3>
          </div>

          <div className="space-y-3">
            {insights?.team_knowledge.map((t, i) => (
              <div
                key={i}
                className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-1"
              >
                <div className="font-bold text-xs text-slate-900 dark:text-white">
                  {t.person}
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-300">
                  {t.summary}
                </p>
                {t.incident_ids?.length > 0 && (
                  <div className="font-mono text-[10px] text-slate-400">
                    Citations: {t.incident_ids.join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Card 4: Fix Speed Comparison */}
        <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center space-x-2 border-b border-slate-200 dark:border-slate-800 pb-3">
            <TrendingUp className="w-4 h-4 text-emerald-500" />
            <h3 className="font-bold text-sm text-slate-900 dark:text-white">
              Mitigation Speed Comparison
            </h3>
          </div>

          {insights?.fix_speed_comparison && (
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-slate-50 dark:bg-slate-800/80 rounded-xl border border-slate-200 dark:border-slate-700">
                  <div className="text-slate-500 text-[11px] mb-1">Rollback Avg MTTR</div>
                  <div className="text-2xl font-extrabold text-slate-900 dark:text-white font-mono">
                    {insights.fix_speed_comparison.first_fix_rollback_avg_min ?? '—'}m
                  </div>
                </div>

                <div className="p-3 bg-slate-50 dark:bg-slate-800/80 rounded-xl border border-slate-200 dark:border-slate-700">
                  <div className="text-slate-500 text-[11px] mb-1">Resize / Reconfig Avg MTTR</div>
                  <div className="text-2xl font-extrabold text-emerald-600 dark:text-emerald-400 font-mono">
                    {insights.fix_speed_comparison.first_fix_resize_avg_min ?? '—'}m
                  </div>
                </div>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 leading-relaxed font-medium">
                {insights.fix_speed_comparison.note}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default InsightsView;
