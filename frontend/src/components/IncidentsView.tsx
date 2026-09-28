import React, { useState, useMemo } from 'react';
import {
  AlertTriangle,
  Plus,
  Search,
  Filter,
  Layers,
  Clock,
  ChevronRight,
  ShieldCheck,
  CheckCircle2,
  Calendar,
} from 'lucide-react';
import { IncidentSummary } from '../types';

interface IncidentsViewProps {
  incidents: IncidentSummary[];
  onSelectIncident: (incidentId: string) => void;
  onOpenNewIncident: () => void;
}

export const IncidentsView: React.FC<IncidentsViewProps> = ({
  incidents,
  onSelectIncident,
  onOpenNewIncident,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [outcomeFilter, setOutcomeFilter] = useState<string>('all');
  const [serviceFilter, setServiceFilter] = useState<string>('all');

  // Extract distinct services
  const distinctServices = useMemo(() => {
    const set = new Set<string>();
    incidents.forEach((inc) => {
      if (inc.service) set.add(inc.service);
    });
    return Array.from(set).sort();
  }, [incidents]);

  // Counts by outcome
  const outcomeCounts = useMemo(() => {
    const counts = {
      all: incidents.length,
      open: 0,
      worked: 0,
      partial: 0,
      failed: 0,
    };
    incidents.forEach((inc) => {
      const o = inc.outcome?.toLowerCase();
      if (o === 'open') counts.open++;
      else if (o === 'worked') counts.worked++;
      else if (o === 'partial') counts.partial++;
      else if (o === 'failed') counts.failed++;
    });
    return counts;
  }, [incidents]);

  // Filtered incidents
  const filteredIncidents = useMemo(() => {
    return incidents.filter((inc) => {
      const term = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !term ||
        inc.incident_id.toLowerCase().includes(term) ||
        inc.title.toLowerCase().includes(term) ||
        inc.service.toLowerCase().includes(term) ||
        (inc.resolver && inc.resolver.toLowerCase().includes(term));

      const matchesSeverity =
        severityFilter === 'all' || inc.severity === severityFilter;

      const matchesOutcome =
        outcomeFilter === 'all' || inc.outcome === outcomeFilter;

      const matchesService =
        serviceFilter === 'all' || inc.service === serviceFilter;

      return matchesSearch && matchesSeverity && matchesOutcome && matchesService;
    });
  }, [incidents, searchQuery, severityFilter, outcomeFilter, serviceFilter]);

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

  return (
    <div className="space-y-6">
      {/* Header Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Incident Directory
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 font-medium">
            Complete historical outages, active alerts, and Hindsight postmortem resolutions
          </p>
        </div>

        <button
          onClick={onOpenNewIncident}
          className="flex items-center space-x-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>New Incident Alert</span>
        </button>
      </div>

      {/* Outcome Tab Filters */}
      <div className="flex items-center space-x-2 border-b border-slate-200 dark:border-slate-800 pb-3 text-xs overflow-x-auto">
        {[
          { id: 'all', label: 'All Incidents', count: outcomeCounts.all },
          { id: 'open', label: 'Open / Active', count: outcomeCounts.open },
          { id: 'worked', label: 'Worked Fix', count: outcomeCounts.worked },
          { id: 'partial', label: 'Partial Fix', count: outcomeCounts.partial },
          { id: 'failed', label: 'Failed Fix', count: outcomeCounts.failed },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setOutcomeFilter(tab.id)}
            className={`px-3 py-1.5 rounded-xl font-bold transition-all flex items-center space-x-2 cursor-pointer ${
              outcomeFilter === tab.id
                ? 'bg-brand-600 text-white shadow-xs'
                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800'
            }`}
          >
            <span>{tab.label}</span>
            <span
              className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                outcomeFilter === tab.id
                  ? 'bg-white/30 text-white'
                  : 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300'
              }`}
            >
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Search & Filter Controls */}
      <div className="bg-white dark:bg-[#161F36] p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-wrap gap-3 items-center justify-between">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by title, incident ID, service or resolver..."
            className="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
          />
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          {/* Severity filter */}
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="px-3 py-2 bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-800 dark:text-slate-200 font-semibold focus:outline-none"
          >
            <option value="all">All Severities</option>
            <option value="SEV1">SEV1</option>
            <option value="SEV2">SEV2</option>
            <option value="SEV3">SEV3</option>
          </select>

          {/* Service filter */}
          <select
            value={serviceFilter}
            onChange={(e) => setServiceFilter(e.target.value)}
            className="px-3 py-2 bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 rounded-xl text-slate-800 dark:text-slate-200 font-semibold focus:outline-none"
          >
            <option value="all">All Services</option>
            {distinctServices.map((svc) => (
              <option key={svc} value={svc}>
                {svc}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Incidents Table / Cards */}
      <div className="bg-white dark:bg-[#161F36] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {filteredIncidents.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">
            No incidents matched your query.
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800/80">
            {filteredIncidents.map((inc) => (
              <div
                key={inc.incident_id}
                onClick={() => onSelectIncident(inc.incident_id)}
                className="p-5 hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition-colors flex items-center justify-between gap-4 group"
              >
                <div className="flex items-start space-x-4 min-w-0">
                  <span
                    className={`w-3 h-3 rounded-full mt-1.5 shrink-0 shadow-xs ${
                      inc.outcome === 'worked'
                        ? 'bg-emerald-500'
                        : inc.outcome === 'partial'
                        ? 'bg-amber-500'
                        : inc.outcome === 'failed'
                        ? 'bg-rose-500'
                        : 'bg-indigo-500 animate-pulse'
                    }`}
                  />
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400 transition-colors truncate">
                      {inc.title}
                    </h3>
                    <div className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-1 flex flex-wrap items-center gap-2">
                      <span className="font-bold text-slate-700 dark:text-slate-300">{inc.incident_id}</span>
                      <span>•</span>
                      <span className="text-brand-600 dark:text-brand-400 font-semibold">{inc.service}</span>
                      {inc.date && (
                        <>
                          <span>•</span>
                          <span>{inc.date.split('T')[0]}</span>
                        </>
                      )}
                      {inc.minutes_to_resolve && (
                        <>
                          <span>•</span>
                          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                            {inc.minutes_to_resolve}m MTTR
                          </span>
                        </>
                      )}
                      {inc.resolver && (
                        <>
                          <span>•</span>
                          <span>Resolver: {inc.resolver}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-3 shrink-0">
                  <span className={`px-2.5 py-0.5 rounded text-xs font-bold border ${getSeverityBadgeClass(inc.severity)}`}>
                    {inc.severity}
                  </span>
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${getOutcomeBadgeClass(inc.outcome)}`}>
                    {inc.outcome}
                  </span>
                  <ChevronRight className="w-5 h-5 text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-200 transition-colors" />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default IncidentsView;
