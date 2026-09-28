import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { TopNav } from './components/TopNav';
import { DashboardView } from './components/DashboardView';
import { IncidentsView } from './components/IncidentsView';
import { IncidentDetailView } from './components/IncidentDetailView';
import { ActivityView } from './components/ActivityView';
import { TeamView } from './components/TeamView';
import { CompareView } from './components/CompareView';
import { InsightsView } from './components/InsightsView';
import { ResolveModal } from './components/ResolveModal';
import { NewIncidentModal } from './components/NewIncidentModal';
import { api } from './services/api';
import {
  Alert,
  AlertResponse,
  HealthResponse,
  IncidentDetail,
  IncidentSummary,
  MetricsResponse,
  RankedFix,
  Warning,
  ActivityItem,
  ResolveResponse,
  parseSeverity,
} from './types';
import {
  AlertCircle,
  Database,
  RotateCcw,
  Sparkles,
  Bot,
  Zap,
} from 'lucide-react';

export const App: React.FC = () => {
  const [currentView, setCurrentView] = useState<string>('dashboard');

  // Backend Health & Telemetry State
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<boolean>(false);
  const [isSeeding, setIsSeeding] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);

  // Core Data State from Real RecallOps APIs
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);

  // Selected Incident for Detail View
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [selectedIncidentDetail, setSelectedIncidentDetail] = useState<IncidentDetail | null>(null);
  const [activeAlertResponse, setActiveAlertResponse] = useState<AlertResponse | null>(null);

  // Modals
  const [isNewIncidentModalOpen, setIsNewIncidentModalOpen] = useState<boolean>(false);
  const [isResolveModalOpen, setIsResolveModalOpen] = useState<boolean>(false);
  const [isSubmittingAlert, setIsSubmittingAlert] = useState<boolean>(false);

  // Fetch initial telemetry and live incidents
  const refreshData = useCallback(async () => {
    try {
      const [h, incs, m] = await Promise.all([
        api.getHealth(),
        api.getIncidents(),
        api.getMetrics().catch(() => null),
      ]);
      setHealth(h);
      setHealthError(false);
      setIncidents(incs);
      if (m) setMetrics(m);

      setActivities((prev) => {
        if (prev.length > 0 || incs.length === 0) return prev;
        return incs.slice(0, 8).map((inc) => ({
          id: `act-init-${inc.incident_id}`,
          timestamp: inc.date ? inc.date.split('T')[0] : 'Historical',
          category: (inc.outcome === 'worked' ? 'resolution' : 'incident') as ActivityItem['category'],
          title: `${inc.incident_id}: ${inc.title}`,
          detail: `Service ${inc.service} (${inc.severity}) • Outcome: ${inc.outcome.toUpperCase()}${inc.minutes_to_resolve ? ` • MTTR: ${inc.minutes_to_resolve}m` : ''}`,
          actor: inc.resolver || 'SRE Team',
          incident_id: inc.incident_id,
          service: inc.service,
          severity: inc.severity,
        }));
      });
    } catch (err) {
      console.warn('Backend connection error:', err);
      setHealthError(true);
    }
  }, []);

  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 10000);
    return () => clearInterval(interval);
  }, [refreshData]);

  // Demo Control: Seed Memory
  const handleSeed = async () => {
    setIsSeeding(true);
    try {
      const res = await api.seed();
      const activity: ActivityItem = {
        id: `act-${Date.now()}`,
        timestamp: 'Just now',
        category: 'memory',
        title: 'Memory Banks Seeded',
        detail: `Successfully retained ${res.seeded} items across incidents, fix-outcomes, and team banks in ${res.duration_s.toFixed(1)}s.`,
        actor: 'Admin',
      };
      setActivities((prev) => [activity, ...prev]);
      await refreshData();
      alert(`Seeded ${res.seeded} items successfully in ${res.duration_s.toFixed(1)}s!`);
    } catch (err: any) {
      alert(`Seed failed: ${err.message}`);
    } finally {
      setIsSeeding(false);
    }
  };

  // Demo Control: Reset Memory
  const handleReset = async () => {
    if (!window.confirm('Reset memory back to freshly seeded baseline state?')) return;
    setIsResetting(true);
    try {
      await api.reset();
      const activity: ActivityItem = {
        id: `act-${Date.now()}`,
        timestamp: 'Just now',
        category: 'memory',
        title: 'Memory Reset to Seed State',
        detail: 'Hindsight live bank cleared and restored to fresh demo seed state.',
        actor: 'Admin',
      };
      setActivities((prev) => [activity, ...prev]);
      await refreshData();
      alert('Memory returned to freshly seeded baseline state.');
    } catch (err: any) {
      alert(`Reset failed: ${err.message}`);
    } finally {
      setIsResetting(false);
    }
  };

  // Select Incident to open detail view
  const handleSelectIncident = async (id: string) => {
    setSelectedIncidentId(id);
    setCurrentView('incident-detail');
    try {
      const detail = await api.getIncident(id);
      setSelectedIncidentDetail(detail);

      // If we don't have an active alert response, construct a synthesized one from detail
      if (!activeAlertResponse || activeAlertResponse.incident_id !== id) {
        setActiveAlertResponse({
          incident_id: detail.incident_id,
          deduplicated: false,
          status: 'open',
          memory_state: 'matched',
          alert: {
            alert_id: detail.incident_id,
            service: detail.service,
            severity: parseSeverity(detail.severity),
            title: detail.title,
            symptoms: detail.symptoms || '',
            error_message: detail.symptoms || 'Error detected',
            log_snippet: detail.log_snippet || '',
          },
          evidence: [],
          ranked_fixes: detail.fix_attempts?.map((f, i) => ({
            rank: i + 1,
            fix_type: f.fix_type,
            label: f.fix_type,
            score: f.outcome === 'worked' ? 1.0 : f.outcome === 'partial' ? 0.5 : 0.0,
            similarity: 0.9,
            worked: f.outcome === 'worked' ? 1 : 0,
            partial: f.outcome === 'partial' ? 1 : 0,
            failed: f.outcome === 'failed' ? 1 : 0,
            attempts: 1,
            recent_failures: f.outcome === 'failed' ? 1 : 0,
          })) || [],
          warnings: [],
          team_hint: detail.resolver ? { person: detail.resolver, reason: 'Previously resolved this service outage', incident_ids: [detail.incident_id] } : null,
          recurrence: null,
          briefing_stream_url: `/incidents/${encodeURIComponent(id)}/briefing/stream`,
        });
      }
    } catch (err) {
      console.warn('Could not load incident detail:', err);
    }
  };

  // Trigger POST /alert
  const handleAlertSubmit = async (alertData: Alert) => {
    setIsSubmittingAlert(true);
    try {
      const res = await api.postAlert(alertData);
      setActiveAlertResponse(res);
      setSelectedIncidentId(res.incident_id);

      // Add to activities
      const act: ActivityItem = {
        id: `act-${Date.now()}`,
        timestamp: 'Just now',
        category: 'incident',
        title: `Alert Ingested: ${res.alert.title}`,
        detail: `Ingested ${res.incident_id} (${res.alert.service} ${res.alert.severity}). Memory state: ${res.memory_state.toUpperCase()}.`,
        actor: 'RecallOps Intake',
        incident_id: res.incident_id,
        service: res.alert.service,
        severity: res.alert.severity,
      };
      setActivities((prev) => [act, ...prev]);

      await refreshData();
      setCurrentView('incident-detail');
    } catch (err: any) {
      alert(`Alert dispatch failed: ${err.message}`);
    } finally {
      setIsSubmittingAlert(false);
    }
  };

  // Feedback received -> update active ranked fixes and log
  const handleFeedbackApplied = (rankedFixes: RankedFix[], warnings: Warning[]) => {
    if (activeAlertResponse) {
      setActiveAlertResponse({
        ...activeAlertResponse,
        ranked_fixes: rankedFixes,
        warnings: warnings,
      });
    }
    const act: ActivityItem = {
      id: `act-${Date.now()}`,
      timestamp: 'Just now',
      category: 'feedback',
      title: 'Fix Feedback Applied (Learning Signal)',
      detail: `Re-ranked ${rankedFixes.length} fixes in real-time. ${warnings.length} hazard warning(s) active.`,
      actor: 'On-Call Engineer',
      incident_id: selectedIncidentId || undefined,
    };
    setActivities((prev) => [act, ...prev]);
    refreshData();
  };

  // Incident resolved
  const handleIncidentResolved = (res: ResolveResponse) => {
    const act: ActivityItem = {
      id: `act-${Date.now()}`,
      timestamp: 'Just now',
      category: 'resolution',
      title: `Incident ${selectedIncidentId} Resolved`,
      detail: `Postmortem generated and permanently stored in Hindsight (${res.memories_stored} items retained).`,
      actor: 'Resolver',
      incident_id: selectedIncidentId || undefined,
    };
    setActivities((prev) => [act, ...prev]);
    refreshData();
  };

  const activeIncidentsCount = incidents.filter((i) => i.outcome === 'open').length;

  return (
    <div className="flex min-h-screen bg-slate-100/70 dark:bg-[#0B0F19] text-slate-900 dark:text-slate-100 font-sans antialiased transition-colors">
      {/* 1. Sidebar */}
      <Sidebar
        currentView={currentView}
        onSelectView={(v) => setCurrentView(v)}
        activeIncidentsCount={activeIncidentsCount}
      />

      {/* 2. Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Navbar */}
        <TopNav
          health={health}
          healthError={healthError}
          incidents={incidents}
          onSelectIncident={handleSelectIncident}
          onSeed={handleSeed}
          onReset={handleReset}
          isSeeding={isSeeding}
          isResetting={isResetting}
        />

        {/* Backend Degraded or Offline Alert Banner */}
        {healthError && (
          <div className="bg-rose-600 text-white px-6 py-2.5 text-xs font-bold flex items-center justify-between shadow-md">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4" />
              <span>
                Backend is unreachable at <code>{api.baseUrl}</code>. Please confirm the FastAPI server is running with <code>uvicorn app.main:app --port 8000</code>.
              </span>
            </div>
            <button
              onClick={refreshData}
              className="px-2.5 py-1 bg-white/20 hover:bg-white/30 rounded font-mono text-[11px] transition-colors cursor-pointer"
            >
              Retry Connection
            </button>
          </div>
        )}

        {/* Page Content */}
        <main className="flex-1 p-8 max-w-7xl w-full mx-auto">
          {/* DASHBOARD VIEW */}
          {currentView === 'dashboard' && (
            <DashboardView
              incidents={incidents}
              metrics={metrics}
              activities={activities}
              onSelectIncident={handleSelectIncident}
              onOpenNewIncident={() => setIsNewIncidentModalOpen(true)}
              onViewAllIncidents={() => setCurrentView('incidents')}
              onViewAllActivity={() => setCurrentView('activity')}
            />
          )}

          {/* INCIDENTS DIRECTORY VIEW */}
          {currentView === 'incidents' && (
            <IncidentsView
              incidents={incidents}
              onSelectIncident={handleSelectIncident}
              onOpenNewIncident={() => setIsNewIncidentModalOpen(true)}
            />
          )}

          {/* INCIDENT DETAIL VIEW */}
          {currentView === 'incident-detail' && (
            <IncidentDetailView
              incidentId={selectedIncidentId || (incidents[0]?.incident_id ?? 'INC-101')}
              incidentDetail={selectedIncidentDetail}
              alertResponse={activeAlertResponse}
              onOpenResolveModal={() => setIsResolveModalOpen(true)}
              onBackToIncidents={() => setCurrentView('incidents')}
              onBackToDashboard={() => setCurrentView('dashboard')}
              onFeedbackApplied={handleFeedbackApplied}
            />
          )}

          {/* COMPARE MODE VIEW */}
          {currentView === 'compare' && <CompareView />}

          {/* PATTERN INSIGHTS VIEW */}
          {currentView === 'insights' && (
            <InsightsView onSelectIncident={handleSelectIncident} />
          )}

          {/* AUDIT & ACTIVITY VIEW */}
          {currentView === 'activity' && (
            <ActivityView
              activities={activities}
              onSelectIncident={handleSelectIncident}
              onOpenNewIncident={() => setIsNewIncidentModalOpen(true)}
            />
          )}

          {/* TEAM & RESPONDERS VIEW */}
          {currentView === 'team' && (
            <TeamView
              teamMembers={[
                { id: 'usr-1', name: 'Priya Nair', email: 'priya.nair@shipfast.internal', role: 'Senior Backend Engineer', team_service: 'payments-api', on_call_status: 'Primary On-Call', initials: 'PN', avatar_color: 'bg-indigo-600', is_lead: true },
                { id: 'usr-2', name: 'Rahul Mehta', email: 'rahul.mehta@shipfast.internal', role: 'Platform Engineer', team_service: 'order-worker', on_call_status: 'Secondary On-Call', initials: 'RM', avatar_color: 'bg-purple-600', is_lead: false },
                { id: 'usr-3', name: 'Ananya Iyer', email: 'ananya.iyer@shipfast.internal', role: 'Site Reliability Engineer', team_service: 'auth-service', on_call_status: 'Available', initials: 'AI', avatar_color: 'bg-emerald-600', is_lead: false },
                { id: 'usr-4', name: 'David Kim', email: 'david.kim@shipfast.internal', role: 'Infra / SRE Lead', team_service: 'infra', on_call_status: 'Available', initials: 'DK', avatar_color: 'bg-teal-600', is_lead: true },
                { id: 'usr-5', name: 'Sofia Martinez', email: 'sofia.martinez@shipfast.internal', role: 'Search Platform Engineer', team_service: 'search-api', on_call_status: 'Available', initials: 'SM', avatar_color: 'bg-amber-600', is_lead: false },
                { id: 'usr-6', name: 'Arjun Verma', email: 'arjun.verma@shipfast.internal', role: 'Backend Engineer', team_service: 'notification-service', on_call_status: 'Off-Duty', initials: 'AV', avatar_color: 'bg-sky-600', is_lead: false },
                { id: 'usr-7', name: 'Vikram Rao', email: 'vikram.rao@shipfast.internal', role: 'Principal Architect', team_service: 'core-platform', on_call_status: 'Available', initials: 'VR', avatar_color: 'bg-rose-600', is_lead: true },
              ]}
              onAddTeamMember={() => {}}
            />
          )}

          {/* DEMO & MEMORY ADMIN (SETTINGS) VIEW */}
          {currentView === 'settings' && (
            <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-6">
              <div>
                <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
                  Demo & Hindsight Memory Administration
                </h1>
                <p className="text-xs text-slate-500 mt-1 font-medium">
                  Direct management of Hindsight Cloud memory banks and benchmark seeds
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 bg-slate-50 dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-3">
                  <div className="flex items-center space-x-2 font-bold text-xs text-slate-900 dark:text-white">
                    <Sparkles className="w-4 h-4 text-brand-500" />
                    <span>Seed Historical Outage Banks</span>
                  </div>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Idempotently retains ~22 seed incidents, fix-outcomes, and team expertise profiles into Hindsight Cloud.
                  </p>
                  <button
                    onClick={handleSeed}
                    disabled={isSeeding || isResetting}
                    className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-bold transition-all cursor-pointer disabled:opacity-50"
                  >
                    {isSeeding ? 'Seeding Hindsight...' : 'Run POST /seed'}
                  </button>
                </div>

                <div className="p-4 bg-slate-50 dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-3">
                  <div className="flex items-center space-x-2 font-bold text-xs text-slate-900 dark:text-white">
                    <RotateCcw className="w-4 h-4 text-rose-500" />
                    <span>Reset Memory to Fresh Baseline</span>
                  </div>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Clears the live retain ledger and resets memory state back to freshly seeded baseline for a clean demo run.
                  </p>
                  <button
                    onClick={handleReset}
                    disabled={isSeeding || isResetting}
                    className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition-all cursor-pointer disabled:opacity-50"
                  >
                    {isResetting ? 'Resetting Memory...' : 'Run POST /reset'}
                  </button>
                </div>
              </div>

              <div className="p-4 bg-slate-50 dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 text-xs space-y-2 font-mono">
                <div className="font-bold text-slate-700 dark:text-slate-300 font-sans">
                  Active Configuration Telemetry:
                </div>
                <div>FastAPI Base: <span className="text-brand-600 dark:text-brand-400">{api.baseUrl}</span></div>
                <div>Memory Status: <span className="text-emerald-600 dark:text-emerald-400 font-bold">{health?.memory ?? 'checking...'}</span></div>
                <div>Cold Seeding Flag: <span>{health?.seeding ? 'TRUE (In Progress)' : 'FALSE (Ready)'}</span></div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Modals */}
      <NewIncidentModal
        isOpen={isNewIncidentModalOpen}
        onClose={() => setIsNewIncidentModalOpen(false)}
        onSubmit={handleAlertSubmit}
        isLoading={isSubmittingAlert}
      />

      <ResolveModal
        isOpen={isResolveModalOpen}
        incidentId={selectedIncidentId || (incidents[0]?.incident_id ?? 'INC-101')}
        onClose={() => setIsResolveModalOpen(false)}
        onResolved={handleIncidentResolved}
      />
    </div>
  );
};

export default App;
