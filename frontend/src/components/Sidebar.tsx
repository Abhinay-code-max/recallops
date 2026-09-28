import React from 'react';
import {
  LayoutDashboard,
  Activity,
  AlertTriangle,
  Bot,
  Users,
  Settings,
  HelpCircle,
  Sun,
  Moon,
  Sparkles,
  GitCompare,
  Lightbulb,
} from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

interface SidebarProps {
  currentView: string;
  onSelectView: (view: string) => void;
  activeIncidentsCount: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentView,
  onSelectView,
  activeIncidentsCount,
}) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <aside
      aria-label="Main Navigation"
      className="w-64 bg-slate-50 dark:bg-[#0E1526] flex-shrink-0 flex flex-col justify-between h-screen sticky top-0 border-r border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 select-none z-30 transition-colors"
    >
      <div>
        {/* Brand / Logo */}
        <div className="h-16 flex items-center px-6 border-b border-slate-200 dark:border-slate-800">
          <button
            type="button"
            className="flex items-center space-x-3 text-left w-full focus:outline-none focus:ring-2 focus:ring-brand-500/20 rounded-lg cursor-pointer"
            onClick={() => onSelectView('dashboard')}
            aria-label="RecallOps Home"
          >
            <div className="w-9 h-9 rounded-xl bg-brand-600 flex items-center justify-center text-white shadow-md shrink-0">
              <Bot className="w-5 h-5" />
            </div>
            <div className="flex flex-col">
              <span className="text-slate-900 dark:text-white font-extrabold tracking-tight text-base flex items-center">
                RecallOps
              </span>
              <span className="text-[10px] text-brand-600 dark:text-brand-400 font-semibold tracking-wide">
                Incident Memory Agent
              </span>
            </div>
          </button>
        </div>

        {/* Navigation Sections */}
        <nav className="px-3 py-4 space-y-5 text-xs" aria-label="Sidebar Sections">
          {/* OVERVIEW */}
          <div>
            <div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              Overview
            </div>
            <div className="space-y-1" role="list">
              <button
                type="button"
                onClick={() => onSelectView('dashboard')}
                aria-label="Navigate to Dashboard"
                aria-current={currentView === 'dashboard' ? 'page' : undefined}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl font-semibold transition-all cursor-pointer ${
                  currentView === 'dashboard'
                    ? 'bg-brand-600 text-white shadow-md'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <LayoutDashboard className="w-4 h-4 shrink-0" />
                <span>Dashboard</span>
              </button>

              <button
                type="button"
                onClick={() => onSelectView('compare')}
                aria-label="Navigate to Compare Mode"
                aria-current={currentView === 'compare' ? 'page' : undefined}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl font-semibold transition-all cursor-pointer ${
                  currentView === 'compare'
                    ? 'bg-brand-600 text-white shadow-md'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <GitCompare className="w-4 h-4 shrink-0 text-cyan-500" />
                <span className="flex-1 text-left">Compare Mode</span>
                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-cyan-100 dark:bg-cyan-950/80 text-cyan-700 dark:text-cyan-300 border border-cyan-300 dark:border-cyan-800">
                  Demo
                </span>
              </button>

              <button
                type="button"
                onClick={() => onSelectView('insights')}
                aria-label="Navigate to Pattern Insights"
                aria-current={currentView === 'insights' ? 'page' : undefined}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl font-semibold transition-all cursor-pointer ${
                  currentView === 'insights'
                    ? 'bg-brand-600 text-white shadow-md'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Lightbulb className="w-4 h-4 shrink-0 text-amber-500" />
                <span>Pattern Insights</span>
              </button>
            </div>
          </div>

          {/* OPERATIONS */}
          <div>
            <div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              Operations
            </div>
            <div className="space-y-1" role="list">
              <button
                type="button"
                onClick={() => onSelectView('incidents')}
                aria-label="Navigate to Incidents directory"
                aria-current={currentView === 'incidents' || currentView === 'incident-detail' ? 'page' : undefined}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl font-semibold transition-all cursor-pointer ${
                  currentView === 'incidents' || currentView === 'incident-detail'
                    ? 'bg-brand-600 text-white shadow-md'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <div className="flex items-center space-x-3">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>Incidents</span>
                </div>
                {activeIncidentsCount > 0 && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      currentView === 'incidents' || currentView === 'incident-detail'
                        ? 'bg-white/25 text-white'
                        : 'bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800'
                    }`}
                  >
                    {activeIncidentsCount}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => onSelectView('activity')}
                aria-label="Navigate to Activity Feed"
                aria-current={currentView === 'activity' ? 'page' : undefined}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl font-semibold transition-all cursor-pointer ${
                  currentView === 'activity'
                    ? 'bg-brand-600 text-white shadow-md'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Activity className="w-4 h-4 shrink-0" />
                <span>Audit & Activity</span>
              </button>
            </div>
          </div>

          {/* ORGANIZATION */}
          <div>
            <div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              Organization
            </div>
            <div className="space-y-1" role="list">
              <button
                type="button"
                onClick={() => onSelectView('team')}
                aria-label="Navigate to Team Management"
                aria-current={currentView === 'team' ? 'page' : undefined}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl font-semibold transition-all cursor-pointer ${
                  currentView === 'team'
                    ? 'bg-brand-600 text-white shadow-md'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Users className="w-4 h-4 shrink-0" />
                <span>Team & Responders</span>
              </button>

              <button
                type="button"
                onClick={() => onSelectView('settings')}
                aria-label="Navigate to Settings and Demo Controls"
                aria-current={currentView === 'settings' ? 'page' : undefined}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl font-semibold transition-all cursor-pointer ${
                  currentView === 'settings'
                    ? 'bg-brand-600 text-white shadow-md'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800/80 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Settings className="w-4 h-4 shrink-0" />
                <span>Demo & Memory Admin</span>
              </button>
            </div>
          </div>
        </nav>
      </div>

      {/* Bottom Footer Actions */}
      <div className="p-3 border-t border-slate-200 dark:border-slate-800 text-xs space-y-1">
        {/* Theme Switcher Button */}
        <button
          type="button"
          onClick={toggleTheme}
          className="w-full flex items-center justify-between px-3 py-2 rounded-xl text-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors border border-slate-200 dark:border-slate-800 font-semibold cursor-pointer"
          title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
          aria-label={`Toggle theme: currently ${theme}`}
        >
          <div className="flex items-center space-x-2.5">
            {theme === 'dark' ? (
              <Sun className="w-4 h-4 text-amber-400" />
            ) : (
              <Moon className="w-4 h-4 text-brand-600" />
            )}
            <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
          </div>
          <span className="text-[9px] uppercase font-mono px-1.5 py-0.5 rounded bg-white dark:bg-slate-900 text-brand-700 dark:text-brand-300 font-bold border border-slate-200 dark:border-slate-700">
            {theme}
          </span>
        </button>

        <div className="px-3 py-2 text-[10px] text-slate-500 dark:text-slate-500 font-mono">
          RecallOps v1 • Hindsight Memory
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
