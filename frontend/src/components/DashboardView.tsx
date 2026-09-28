import React from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Bot,
  Plus,
  ChevronRight,
  TrendingDown,
  Database,
  Brain,
  Sparkles,
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts';
import { IncidentSummary, MetricsResponse, ActivityItem } from '../types';

interface DashboardViewProps {
  incidents: IncidentSummary[];
  metrics: MetricsResponse | null;
  activities: ActivityItem[];
  onSelectIncident: (incidentId: string) => void;
  onOpenNewIncident: () => void;
  onViewAllIncidents?: () => void;
  onViewAllActivity?: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  incidents,
  metrics,
  activities,
  onSelectIncident,
  onOpenNewIncident,
  onViewAllIncidents,
  onViewAllActivity,
}) => {
  const activeCount = incidents.filter((inc) => inc.outcome === 'open').length;

  const getSeverityBadgeClass = (sev: string) => {
    switch (sev) {
      case 'SEV1':
        return 'bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border-rose-300 dark:border-rose-800';
      case 'SEV2':
        return 'bg-amber-100 dark:bg-amber-950/80 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-800';
      case 'SEV3':
        return 'bg-blue-100 dark:bg-blue-950/80 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-800';
      default:
        return 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700';
    }
  };

  const getOutcomeBadgeClass = (outcome: string) => {
    switch (outcome) {
      case 'worked':
        return 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800';
      case 'partial':
        return 'bg-amber-100 dark:bg-amber-950/80 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-800';
      case 'failed':
        return 'bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border-rose-300 dark:border-rose-800';
      case 'open':
      default:
        return 'bg-indigo-100 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300 border-indigo-300 dark:border-indigo-800';
    }
  };

  // Prepare combined learning curve chart data
  const chartData = React.useMemo(() => {
    if (!metrics) return [];
    const maxLen = Math.max(metrics.real_series.length, metrics.simulated_series.length);
    const points = [];
    for (let i = 0; i < maxLen; i++) {
      const real = metrics.real_series[i];
      const sim = metrics.simulated_series[i];
      points.push({
        incident: `Inc #${i + 1}`,
        real_mttr: real?.mttr_min ?? null,
        simulated_mttr: sim?.mttr_min ?? null,
        simulated_accuracy: sim?.accuracy ? `${Math.round(sim.accuracy * 100)}%` : undefined,
      });
    }
    return points;
  }, [metrics]);

  return (
    <div className="space-y-6" role="region" aria-label="Incident Response Cockpit">
      {/* Header Row */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Incident Cockpit & Learning Metrics
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 font-medium">
            Real-time decision support, Hindsight memory banks, and MTTR reduction telemetry
          </p>
        </div>

        <button
          onClick={onOpenNewIncident}
          className="flex items-center space-x-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer"
        >
          <Plus className="w-4 h-4" />
          <span>New Alert / Incident</span>
        </button>
      </div>

      {/* 4 Real Metric Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Card 1: Active Incidents */}
        <div className="bg-white dark:bg-[#161F36] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-lg flex flex-col justify-between hover:shadow-md transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="w-10 h-10 rounded-xl bg-rose-50 dark:bg-rose-950/70 border border-rose-200 dark:border-rose-900/80 flex items-center justify-center text-rose-600 dark:text-rose-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <span
              className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${
                activeCount > 0
                  ? 'bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border-rose-300 dark:border-rose-800'
                  : 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800'
              }`}
            >
              {activeCount > 0 ? `${activeCount} Active` : 'All Clear'}
            </span>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-slate-900 dark:text-white font-sans tracking-tight">
              {activeCount}
            </div>
            <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mt-1">
              Active Incidents
            </div>
          </div>
        </div>

        {/* Card 2: Memories Stored */}
        <div className="bg-white dark:bg-[#161F36] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-lg flex flex-col justify-between hover:shadow-md transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-950/70 border border-indigo-200 dark:border-indigo-900/80 flex items-center justify-center text-brand-600 dark:text-brand-400">
              <Database className="w-5 h-5" />
            </div>
            <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-indigo-100 dark:bg-indigo-950/80 text-brand-700 dark:text-brand-300 border border-brand-300 dark:border-brand-800">
              Hindsight Banks
            </span>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-slate-900 dark:text-white font-sans tracking-tight">
              {metrics?.counts.memories_stored ?? '—'}
            </div>
            <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mt-1">
              Memories Stored & Retained
            </div>
          </div>
        </div>

        {/* Card 3: Historical Avg MTTR */}
        <div className="bg-white dark:bg-[#161F36] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-lg flex flex-col justify-between hover:shadow-md transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-950/70 border border-emerald-200 dark:border-emerald-900/80 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
              <Clock className="w-5 h-5" />
            </div>
            <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800">
              Baseline
            </span>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-slate-900 dark:text-white font-sans tracking-tight flex items-baseline gap-2">
              <span>{metrics ? `${Math.round(metrics.historical_avg_mttr_min)}m` : '—'}</span>
            </div>
            <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mt-1">
              Historical Avg MTTR
            </div>
          </div>
        </div>

        {/* Card 4: Total Incidents Handled */}
        <div className="bg-white dark:bg-[#161F36] p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-lg flex flex-col justify-between hover:shadow-md transition-all">
          <div className="flex items-center justify-between mb-4">
            <div className="w-10 h-10 rounded-xl bg-brand-50 dark:bg-brand-950/70 border border-brand-200 dark:border-brand-900/80 flex items-center justify-center text-brand-600 dark:text-brand-400">
              <Bot className="w-5 h-5" />
            </div>
            <span className="px-2.5 py-1 rounded-full text-[11px] font-bold bg-brand-100 dark:bg-brand-950/80 text-brand-700 dark:text-brand-300 border border-brand-300 dark:border-brand-800">
              Learned Outages
            </span>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-slate-900 dark:text-white font-sans tracking-tight">
              {metrics?.counts.incidents_handled ?? incidents.length}
            </div>
            <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 mt-1">
              Total Incidents Handled
            </div>
          </div>
        </div>
      </div>

      {/* Learning Curve Dashboard (Recharts): Real vs Simulated Series */}
      {chartData.length > 0 && (
        <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-lg transition-colors">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-2">
            <div>
              <div className="flex items-center space-x-2">
                <TrendingDown className="w-5 h-5 text-emerald-500" />
                <h3 className="font-extrabold text-base text-slate-900 dark:text-white">
                  Agent Learning Curve: MTTR Over Successive Incidents
                </h3>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Comparing historical unassisted resolution time with RecallOps memory-accelerated MTTR
              </p>
            </div>
            <div className="flex items-center space-x-3 text-xs">
              <span className="flex items-center space-x-1.5 font-bold text-slate-600 dark:text-slate-300">
                <span className="w-3 h-3 rounded-full bg-slate-400" />
                <span>Historical Seed MTTR</span>
              </span>
              <span className="flex items-center space-x-1.5 font-bold text-brand-600 dark:text-brand-400">
                <span className="w-3 h-3 rounded-full bg-indigo-500" />
                <span>SIMULATED (RecallOps)</span>
              </span>
            </div>
          </div>

          <div className="h-64 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                <XAxis dataKey="incident" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                <YAxis
                  unit="m"
                  tick={{ fontSize: 11, fill: '#94a3b8' }}
                  label={{ value: 'Minutes to Resolve', angle: -90, position: 'insideLeft', offset: 15, style: { fontSize: 10, fill: '#64748b' } }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '0.75rem',
                    fontSize: '12px',
                    color: '#f8fafc',
                  }}
                  formatter={(value: any, name: any) => [
                    `${value} min`,
                    name === 'real_mttr' ? 'Historical MTTR' : 'SIMULATED RecallOps MTTR',
                  ]}
                />
                <Legend
                  formatter={(value) =>
                    value === 'real_mttr' ? 'Historical MTTR' : 'SIMULATED RecallOps MTTR'
                  }
                />
                <Line
                  type="monotone"
                  dataKey="real_mttr"
                  name="real_mttr"
                  stroke="#94a3b8"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
                <Line
                  type="monotone"
                  dataKey="simulated_mttr"
                  name="simulated_mttr"
                  stroke="#6366f1"
                  strokeWidth={3}
                  dot={{ r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 text-[11px] text-slate-500 font-mono text-center">
            * Note: Series labelled <strong className="text-brand-600 dark:text-brand-400">SIMULATED</strong> represents modeled agent learning trajectory from spec seed benchmarks.
          </div>
        </div>
      )}

      {/* Main Content Area: Recent Incidents & Activity Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Recent Incidents (8 Cols) */}
        <div className="lg:col-span-8 bg-white dark:bg-[#161F36] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-lg overflow-hidden transition-colors">
          <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <h3 className="font-bold text-base text-slate-900 dark:text-white">Recent Incidents</h3>
            {onViewAllIncidents && (
              <button
                type="button"
                onClick={onViewAllIncidents}
                className="text-xs font-bold text-brand-600 dark:text-brand-400 hover:underline transition-colors cursor-pointer"
              >
                View all ({incidents.length})
              </button>
            )}
          </div>

          <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
            {incidents.slice(0, 6).map((inc) => (
              <div
                key={inc.incident_id}
                onClick={() => onSelectIncident(inc.incident_id)}
                className="p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition-colors flex items-center justify-between gap-4 group"
              >
                <div className="flex items-start space-x-3.5">
                  <span
                    className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 shadow-xs ${
                      inc.outcome === 'worked'
                        ? 'bg-emerald-500'
                        : inc.outcome === 'partial'
                        ? 'bg-amber-500'
                        : inc.outcome === 'failed'
                        ? 'bg-rose-500'
                        : 'bg-indigo-500 animate-pulse'
                    }`}
                  />
                  <div>
                    <h4 className="text-xs font-bold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">
                      {inc.title}
                    </h4>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 font-mono mt-0.5 flex items-center space-x-2">
                      <span>{inc.incident_id}</span>
                      <span>•</span>
                      <span>{inc.service}</span>
                      {inc.minutes_to_resolve && (
                        <>
                          <span>•</span>
                          <span>{inc.minutes_to_resolve} min MTTR</span>
                        </>
                      )}
                      {inc.resolver && (
                        <>
                          <span>•</span>
                          <span className="font-sans text-slate-700 dark:text-slate-300">
                            Fixed by {inc.resolver}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-2.5 shrink-0">
                  <span className={`px-2 py-0.5 rounded text-[11px] font-bold border ${getSeverityBadgeClass(inc.severity)}`}>
                    {inc.severity}
                  </span>
                  <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${getOutcomeBadgeClass(inc.outcome)}`}>
                    {inc.outcome}
                  </span>
                  <ChevronRight className="w-4 h-4 text-slate-400 dark:text-slate-500 group-hover:text-slate-700 dark:group-hover:text-slate-200 transition-colors" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Activity Feed (4 Cols) */}
        <div className="lg:col-span-4 bg-white dark:bg-[#161F36] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm dark:shadow-lg overflow-hidden flex flex-col transition-colors">
          <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <h3 className="font-bold text-base text-slate-900 dark:text-white">Audit & Activity Log</h3>
            {onViewAllActivity && (
              <button
                type="button"
                onClick={onViewAllActivity}
                className="text-xs font-bold text-brand-600 dark:text-brand-400 hover:underline transition-colors cursor-pointer"
              >
                View all ({activities.length})
              </button>
            )}
          </div>

          <div className="p-5 space-y-4 flex-1 overflow-y-auto max-h-[460px]">
            {activities.length === 0 ? (
              <div className="text-xs text-slate-400 text-center py-6">No recent actions recorded.</div>
            ) : (
              activities.slice(0, 7).map((item) => (
                <div
                  key={item.id}
                  onClick={() => item.incident_id && onSelectIncident(item.incident_id)}
                  className={`flex items-start space-x-3 relative ${
                    item.incident_id ? 'cursor-pointer group' : ''
                  }`}
                >
                  <span className="w-3.5 h-3.5 rounded-full shrink-0 mt-0.5 z-10 border-2 border-white dark:border-[#161F36] shadow-xs bg-brand-600" />
                  <div className="text-xs space-y-0.5 flex-1 min-w-0">
                    <div className="text-slate-900 dark:text-slate-100 flex items-center justify-between">
                      <span className="font-bold truncate text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors">
                        {item.title}
                      </span>
                      <span className="text-slate-400 dark:text-slate-500 font-mono text-[10px] shrink-0 ml-2">
                        {item.timestamp}
                      </span>
                    </div>
                    <div className="text-slate-600 dark:text-slate-400 text-[11px] font-medium line-clamp-2">
                      {item.detail}
                    </div>
                    <div className="text-slate-400 text-[10px]">
                      By <strong className="text-slate-600 dark:text-slate-300">{item.actor}</strong>
                      {item.incident_id && (
                        <span className="ml-1 font-mono text-brand-600 dark:text-brand-400 font-semibold">
                          • {item.incident_id}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardView;
