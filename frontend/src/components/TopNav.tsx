import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
  Search,
  Database,
  Sparkles,
  AlertCircle,
  RefreshCw,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { IncidentSummary, HealthResponse } from '../types';

interface TopNavProps {
  health: HealthResponse | null;
  healthError: boolean;
  incidents: IncidentSummary[];
  onSelectIncident: (incidentId: string) => void;
  onSeed: () => void;
  onReset: () => void;
  isSeeding: boolean;
  isResetting: boolean;
}

export const TopNav: React.FC<TopNavProps> = ({
  health,
  healthError,
  incidents,
  onSelectIncident,
  onSeed,
  onReset,
  isSeeding,
  isResetting,
}) => {
  const [searchVal, setSearchVal] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  // Filter incidents across multiple fields
  const searchResults = useMemo(() => {
    const term = searchVal.trim().toLowerCase();
    if (!term) return [];

    return incidents.filter((inc) => {
      return (
        inc.incident_id.toLowerCase().includes(term) ||
        inc.title.toLowerCase().includes(term) ||
        inc.service.toLowerCase().includes(term) ||
        inc.severity.toLowerCase().includes(term) ||
        (inc.resolver && inc.resolver.toLowerCase().includes(term))
      );
    });
  }, [incidents, searchVal]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(event.target as Node)
      ) {
        setIsSearchOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getMemoryBadge = () => {
    if (healthError || !health) {
      return (
        <span className="flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800">
          <AlertCircle className="w-3.5 h-3.5" />
          <span>Backend Offline</span>
        </span>
      );
    }
    if (health.seeding || isSeeding) {
      return (
        <span className="flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-blue-100 dark:bg-blue-950/80 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-800 animate-pulse">
          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          <span>Memory Seeding...</span>
        </span>
      );
    }
    if (health.memory === 'down') {
      return (
        <span className="flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800">
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>Memory Down</span>
        </span>
      );
    }
    if (health.memory === 'slow') {
      return (
        <span className="flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 dark:bg-amber-950/80 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800">
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>Memory Slow</span>
        </span>
      );
    }
    return (
      <span className="flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800">
        <CheckCircle2 className="w-3.5 h-3.5" />
        <span>Hindsight Connected</span>
      </span>
    );
  };

  return (
    <header className="h-16 bg-white dark:bg-[#111625] border-b border-slate-200 dark:border-slate-800/80 px-6 flex items-center justify-between sticky top-0 z-40 transition-colors shadow-xs">
      {/* Global Search */}
      <div className="relative w-96" ref={searchContainerRef}>
        <div className="relative flex items-center">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 pointer-events-none" />
          <input
            type="text"
            value={searchVal}
            onChange={(e) => {
              setSearchVal(e.target.value);
              setIsSearchOpen(true);
            }}
            onFocus={() => setIsSearchOpen(true)}
            placeholder="Search incidents, services, resolvers..."
            className="w-full pl-9 pr-4 py-2 bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/80 rounded-xl text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all font-medium"
          />
        </div>

        {/* Dropdown Results */}
        {isSearchOpen && searchVal.trim() && (
          <div className="absolute left-0 right-0 mt-2 bg-white dark:bg-[#161F36] border border-slate-200 dark:border-slate-700 rounded-2xl shadow-xl z-50 overflow-hidden max-h-72 overflow-y-auto">
            {searchResults.length === 0 ? (
              <div className="p-4 text-xs text-slate-500 text-center">No matching incidents found</div>
            ) : (
              searchResults.map((inc) => (
                <button
                  key={inc.incident_id}
                  onClick={() => {
                    onSelectIncident(inc.incident_id);
                    setIsSearchOpen(false);
                    setSearchVal('');
                  }}
                  className="w-full text-left p-3 hover:bg-slate-50 dark:hover:bg-slate-800/80 border-b border-slate-100 dark:border-slate-800/50 flex items-center justify-between transition-colors cursor-pointer"
                >
                  <div className="min-w-0 pr-2">
                    <div className="text-xs font-bold text-slate-900 dark:text-white truncate">
                      {inc.title}
                    </div>
                    <div className="text-[11px] text-slate-500 font-mono flex items-center space-x-2 mt-0.5">
                      <span>{inc.incident_id}</span>
                      <span>•</span>
                      <span>{inc.service}</span>
                    </div>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                      inc.severity === 'SEV1'
                        ? 'bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300'
                        : inc.severity === 'SEV2'
                        ? 'bg-amber-100 dark:bg-amber-950/80 text-amber-700 dark:text-amber-300'
                        : 'bg-blue-100 dark:bg-blue-950/80 text-blue-700 dark:text-blue-300'
                    }`}
                  >
                    {inc.severity}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      {/* Right Controls: Health Badge & Demo Seed/Reset */}
      <div className="flex items-center space-x-3">
        {/* Memory Health Pill */}
        {getMemoryBadge()}

        {/* Demo Controls */}
        <div className="flex items-center space-x-1.5 border-l border-slate-200 dark:border-slate-800 pl-3">
          <button
            onClick={onSeed}
            disabled={isSeeding || isResetting}
            title="Seed Hindsight memory banks with historical outages"
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors border border-slate-200 dark:border-slate-700 cursor-pointer disabled:opacity-50"
          >
            <Sparkles className="w-3.5 h-3.5 text-brand-600 dark:text-brand-400" />
            <span>{isSeeding ? 'Seeding...' : 'Seed'}</span>
          </button>

          <button
            onClick={onReset}
            disabled={isSeeding || isResetting}
            title="Reset memory to freshly seeded state"
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors border border-slate-200 dark:border-slate-700 cursor-pointer disabled:opacity-50"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
            <span>{isResetting ? 'Resetting...' : 'Reset'}</span>
          </button>
        </div>
      </div>
    </header>
  );
};

export default TopNav;
