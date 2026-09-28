import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  Bot,
  Terminal,
  Activity,
  Zap,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
  Clock,
  ExternalLink,
  ChevronDown,
  Info,
  RefreshCw,
  BookOpen,
} from 'lucide-react';
import {
  Alert,
  AlertResponse,
  IncidentDetail,
  BriefingSections,
  RankedFix,
  Evidence,
  Warning,
  TeamHint,
  Recurrence,
  ChatMessage,
  parseSeverity,
} from '../types';
import { api } from '../services/api';

interface IncidentDetailViewProps {
  incidentId: string;
  incidentDetail: IncidentDetail | null;
  alertResponse: AlertResponse | null;
  onOpenResolveModal: () => void;
  onBackToIncidents: () => void;
  onBackToDashboard: () => void;
  onFeedbackApplied: (rankedFixes: RankedFix[], warnings: Warning[]) => void;
}

export const IncidentDetailView: React.FC<IncidentDetailViewProps> = ({
  incidentId,
  incidentDetail,
  alertResponse,
  onOpenResolveModal,
  onBackToIncidents,
  onBackToDashboard,
  onFeedbackApplied,
}) => {
  // Live Alert & Memory State
  const incidentAlert: Alert = alertResponse?.alert || {
    service: incidentDetail?.service || 'service',
    severity: parseSeverity(incidentDetail?.severity),
    title: incidentDetail?.title || incidentId,
    error_message: incidentDetail?.symptoms || 'Service degraded',
    log_snippet: incidentDetail?.log_snippet || '',
    deploy: null,
    error_signature: null,
  };

  const [streamingText, setStreamingText] = useState<string>('');
  const [briefingSections, setBriefingSections] = useState<BriefingSections | null>(null);
  const [citedIds, setCitedIds] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  // Ranked Fixes & Warnings state (updated live via Feedback)
  const [rankedFixes, setRankedFixes] = useState<RankedFix[]>(
    alertResponse?.ranked_fixes || []
  );
  const [warnings, setWarnings] = useState<Warning[]>(
    alertResponse?.warnings || []
  );

  useEffect(() => {
    if (alertResponse?.ranked_fixes) {
      setRankedFixes(alertResponse.ranked_fixes);
    }
    if (alertResponse?.warnings) {
      setWarnings(alertResponse.warnings);
    }
  }, [alertResponse]);

  // SSE Stream Briefing on mount or alertResponse change
  useEffect(() => {
    if (!alertResponse?.briefing_stream_url) return;

    setStreamingText('');
    setBriefingSections(null);
    setCitedIds([]);
    setIsStreaming(true);
    setStreamError(null);

    const cleanup = api.streamBriefing(alertResponse.briefing_stream_url, {
      onToken: (token) => {
        setStreamingText((prev) => prev + token);
      },
      onSections: (sections) => {
        setBriefingSections(sections);
      },
      onDone: (cited) => {
        setCitedIds(cited);
        setIsStreaming(false);
      },
      onError: (err) => {
        setStreamError(err);
        setIsStreaming(false);
      },
    });

    return cleanup;
  }, [alertResponse?.briefing_stream_url]);

  // Chat State
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isSendingChat, setIsSendingChat] = useState(false);

  // Submitting Feedback
  const [submittingFix, setSubmittingFix] = useState<string | null>(null);

  const handleFeedback = async (fixType: string, outcome: 'worked' | 'partial' | 'failed') => {
    setSubmittingFix(`${fixType}-${outcome}`);
    try {
      const res = await api.postFeedback({
        incident_id: incidentId,
        fix_type: fixType,
        outcome,
      });
      setRankedFixes(res.ranked_fixes);
      setWarnings(res.warnings);
      onFeedbackApplied(res.ranked_fixes, res.warnings);
    } catch (err: any) {
      window.alert(`Feedback submission failed: ${err.message}`);
    } finally {
      setSubmittingFix(null);
    }
  };

  const handleSendChat = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || isSendingChat) return;

    const question = chatInput.trim();
    setChatInput('');
    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: 'user',
      content: question,
      timestamp: new Date().toLocaleTimeString(),
    };
    setChatMessages((prev) => [...prev, userMsg]);
    setIsSendingChat(true);

    try {
      const res = await api.sendChat({
        incident_id: incidentId,
        question,
      });
      const assistantMsg: ChatMessage = {
        id: `ast-${Date.now()}`,
        role: 'assistant',
        content: res.answer,
        timestamp: new Date().toLocaleTimeString(),
        evidence: res.evidence,
      };
      setChatMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: `Error retrieving grounded answer: ${err.message}`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSendingChat(false);
    }
  };

  const evidenceList: Evidence[] = alertResponse?.evidence || [];
  const recurrence: Recurrence | null = alertResponse?.recurrence || null;
  const teamHint: TeamHint | null = alertResponse?.team_hint || null;

  return (
    <div className="space-y-6">
      {/* Top Breadcrumbs */}
      <div className="flex items-center space-x-2 text-xs text-slate-500 dark:text-slate-400 font-medium">
        <button
          onClick={onBackToIncidents}
          className="flex items-center space-x-1 text-brand-600 dark:text-brand-400 hover:underline font-bold transition-colors cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Incidents</span>
        </button>
        <span>/</span>
        <button onClick={onBackToDashboard} className="hover:underline text-slate-500 cursor-pointer">
          Dashboard
        </button>
        <span>/</span>
        <span className="font-mono text-slate-800 dark:text-slate-200 font-bold">{incidentId}</span>
      </div>

      {/* Incident Detail Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">
              {incidentAlert.title}
            </h1>
            <span
              className={`px-2.5 py-0.5 rounded-full text-xs font-extrabold ${
                incidentAlert.severity === 'SEV1'
                  ? 'bg-rose-100 dark:bg-rose-950/80 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800'
                  : incidentAlert.severity === 'SEV2'
                  ? 'bg-amber-100 dark:bg-amber-950/80 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800'
                  : 'bg-blue-100 dark:bg-blue-950/80 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-800'
              }`}
            >
              {incidentAlert.severity}
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 font-mono mt-1">
            Service: <strong className="text-brand-600 dark:text-brand-400">{incidentAlert.service}</strong>
            {incidentAlert.deploy && <span> • Deploy: {incidentAlert.deploy}</span>}
            {incidentAlert.error_signature && <span> • Signature: {incidentAlert.error_signature}</span>}
            {alertResponse?.memory_state && (
              <span> • Memory state: <strong className="uppercase">{alertResponse.memory_state}</strong></span>
            )}
          </p>
        </div>

        {/* Action Button: Mark Resolved */}
        <div className="flex items-center space-x-3">
          <button
            onClick={onOpenResolveModal}
            className="flex items-center space-x-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer"
          >
            <ShieldCheck className="w-4 h-4" />
            <span>Resolve & Retain Postmortem</span>
          </button>
        </div>
      </div>

      {/* Warnings & Team Hints Banner Area */}
      {(warnings.length > 0 || teamHint || recurrence) && (
        <div className="space-y-3">
          {warnings.map((w, idx) => (
            <div
              key={idx}
              className="p-4 rounded-2xl bg-rose-50 dark:bg-rose-950/60 border border-rose-300 dark:border-rose-800 text-xs flex items-start space-x-3"
            >
              <AlertTriangle className="w-5 h-5 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-extrabold text-rose-800 dark:text-rose-200">
                  CRITICAL FAILURE WARNING ({w.kind})
                </div>
                <div className="text-rose-700 dark:text-rose-300 font-medium mt-0.5 leading-relaxed">
                  {w.message}
                </div>
                {w.incident_ids?.length > 0 && (
                  <div className="font-mono text-[11px] text-rose-600 dark:text-rose-400 mt-1">
                    Citations: {w.incident_ids.join(', ')}
                  </div>
                )}
              </div>
            </div>
          ))}

          {recurrence && (
            <div className="p-4 rounded-2xl bg-amber-50 dark:bg-amber-950/60 border border-amber-300 dark:border-amber-800 text-xs flex items-start space-x-3">
              <Clock className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-extrabold text-amber-800 dark:text-amber-200">
                  RECURRENCE DETECTED (#{recurrence.occurrence_number})
                </div>
                <div className="text-amber-700 dark:text-amber-300 font-medium mt-0.5">
                  {recurrence.message}
                </div>
                {recurrence.open_permanent_fix_incident_id && (
                  <div className="font-mono text-[11px] text-amber-700 dark:text-amber-300 mt-1">
                    Open permanent fix tracked in: {recurrence.open_permanent_fix_incident_id}
                  </div>
                )}
              </div>
            </div>
          )}

          {teamHint && (
            <div className="p-4 rounded-2xl bg-blue-50 dark:bg-blue-950/60 border border-blue-300 dark:border-blue-800 text-xs flex items-start space-x-3">
              <Users className="w-5 h-5 text-blue-600 dark:text-blue-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-extrabold text-blue-800 dark:text-blue-200">
                  TEAM EXPERTISE HINT
                </div>
                <div className="text-blue-700 dark:text-blue-300 font-medium mt-0.5">
                  <strong>{teamHint.person}</strong>: {teamHint.reason}
                </div>
                {teamHint.incident_ids?.length > 0 && (
                  <div className="font-mono text-[11px] text-blue-600 dark:text-blue-400 mt-1">
                    Relevant incidents resolved: {teamHint.incident_ids.join(', ')}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Main Grid: Left Column (Briefing + Evidence + Chat) & Right Column (Ranked Fixes + Log) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (7 Cols): Streaming Briefing, Grounded Chat, Evidence */}
        <div className="lg:col-span-7 space-y-6">
          {/* Triage Briefing (SSE streaming) */}
          <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <Sparkles className="w-4 h-4 text-brand-500" />
                <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                  Triage Briefing (Hindsight Grounded)
                </h3>
              </div>
              {isStreaming && (
                <span className="flex items-center space-x-1.5 text-xs text-brand-600 dark:text-brand-400 font-semibold animate-pulse">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Streaming text...</span>
                </span>
              )}
            </div>

            {streamError && (
              <div className="text-xs text-rose-600 bg-rose-50 dark:bg-rose-950/60 p-3 rounded-xl border border-rose-200">
                {streamError}
              </div>
            )}

            {/* Display structured sections if available, or streaming text buffer */}
            {briefingSections ? (
              <div className="space-y-3.5 text-xs leading-relaxed">
                <div>
                  <span className="font-extrabold uppercase text-[10px] tracking-wider text-slate-400 block mb-1">
                    Likely Root Cause
                  </span>
                  <p className="text-slate-800 dark:text-slate-200 font-medium">
                    {briefingSections.root_cause}
                  </p>
                  {briefingSections.sources?.root_cause?.length > 0 && (
                    <span className="font-mono text-[10px] text-brand-600 dark:text-brand-400">
                      Sources: {briefingSections.sources.root_cause.join(', ')}
                    </span>
                  )}
                </div>

                <div>
                  <span className="font-extrabold uppercase text-[10px] tracking-wider text-slate-400 block mb-1">
                    Blast Radius
                  </span>
                  <p className="text-slate-800 dark:text-slate-200 font-medium">
                    {briefingSections.blast_radius}
                  </p>
                </div>

                <div>
                  <span className="font-extrabold uppercase text-[10px] tracking-wider text-slate-400 block mb-1">
                    First 3 Immediate Actions
                  </span>
                  <ol className="list-decimal list-inside space-y-1 text-slate-800 dark:text-slate-200 font-medium">
                    {briefingSections.first_actions.map((act, i) => (
                      <li key={i}>{act}</li>
                    ))}
                  </ol>
                  {briefingSections.sources?.first_actions?.length > 0 && (
                    <span className="font-mono text-[10px] text-brand-600 dark:text-brand-400">
                      Sources: {briefingSections.sources.first_actions.join(', ')}
                    </span>
                  )}
                </div>

                {briefingSections.last_fixed_by && (
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 font-mono text-[11px] text-slate-500">
                    Last successfully fixed by:{' '}
                    <strong className="text-slate-800 dark:text-slate-200 font-sans">
                      {briefingSections.last_fixed_by}
                    </strong>
                  </div>
                )}
              </div>
            ) : streamingText ? (
              <div className="text-xs text-slate-800 dark:text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
                {streamingText}
              </div>
            ) : (
              <div className="text-xs text-slate-400 py-3">
                No briefing stream available for this incident yet.
              </div>
            )}

            {citedIds.length > 0 && (
              <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-[11px] font-mono text-slate-500">
                Validated Citations: {citedIds.join(', ')}
              </div>
            )}
          </div>

          {/* Recalled Memory Evidence Panel */}
          <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center space-x-2 border-b border-slate-200 dark:border-slate-800 pb-3">
              <BookOpen className="w-4 h-4 text-brand-500" />
              <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                Memory Evidence Panel ({evidenceList.length} recalled hits)
              </h3>
            </div>

            {evidenceList.length === 0 ? (
              <div className="text-xs text-slate-400 py-4 text-center">
                No prior memory match found (cold start / novel incident).
              </div>
            ) : (
              <div className="space-y-3">
                {evidenceList.map((ev, i) => (
                  <div
                    key={i}
                    className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 space-y-1.5"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center space-x-2">
                        <span className="font-mono font-bold text-brand-600 dark:text-brand-400">
                          {ev.incident_id}
                        </span>
                        <span className="text-slate-400">•</span>
                        <span className="text-slate-600 dark:text-slate-300 font-medium">
                          {ev.relative}
                        </span>
                        {ev.service && (
                          <>
                            <span className="text-slate-400">•</span>
                            <span className="text-slate-500">{ev.service}</span>
                          </>
                        )}
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-100 dark:bg-indigo-950 text-brand-700 dark:text-brand-300 border border-brand-200 dark:border-brand-800">
                        {Math.round(ev.relevance * 100)}% match
                      </span>
                    </div>

                    <p className="text-xs text-slate-700 dark:text-slate-300 font-mono leading-relaxed bg-white dark:bg-slate-900 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 whitespace-pre-wrap">
                      {ev.excerpt}
                    </p>

                    <div className="text-[10px] text-slate-400 font-mono flex items-center justify-between">
                      <span>Bank: {ev.source_bank}</span>
                      {ev.date && <span>Date: {ev.date.split('T')[0]}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Grounded Follow-up Chat */}
          <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center space-x-2 border-b border-slate-200 dark:border-slate-800 pb-3">
              <Bot className="w-4 h-4 text-brand-500" />
              <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                Grounded Q&A Follow-up
              </h3>
            </div>

            <div className="max-h-60 overflow-y-auto space-y-3 pr-1 text-xs">
              {chatMessages.length === 0 ? (
                <div className="text-slate-400 text-center py-4">
                  Ask questions grounded in historical memory (e.g., "Has this happened after a deploy before?", "Who fixed this in 2025?")
                </div>
              ) : (
                chatMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`p-3 rounded-xl leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-slate-100 dark:bg-slate-800/80 text-slate-900 dark:text-white ml-8 font-medium'
                        : 'bg-brand-50/70 dark:bg-brand-950/60 border border-brand-200 dark:border-brand-900 text-slate-800 dark:text-slate-100 mr-4'
                    }`}
                  >
                    <div className="font-bold text-[11px] mb-1 text-slate-500 dark:text-slate-400">
                      {msg.role === 'user' ? 'You' : 'RecallOps Agent'} • {msg.timestamp}
                    </div>
                    <div>{msg.content}</div>
                    {msg.evidence && msg.evidence.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-brand-200 dark:border-brand-900 font-mono text-[10px] text-brand-600 dark:text-brand-400">
                        Citations: {msg.evidence.map((e) => e.incident_id).join(', ')}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <form onSubmit={handleSendChat} className="flex gap-2 pt-2">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask grounded question..."
                className="flex-1 px-3.5 py-2.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
              />
              <button
                type="submit"
                disabled={isSendingChat || !chatInput.trim()}
                className="px-4 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-xl text-xs font-bold shadow-sm transition-all disabled:opacity-50 cursor-pointer flex items-center space-x-1"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Ask</span>
              </button>
            </form>
          </div>
        </div>

        {/* Right Column (5 Cols): Ranked Fixes + Live Feedback Buttons + Raw Logs */}
        <div className="lg:col-span-5 space-y-6">
          {/* Outcome-Ranked Fixes with Worked/Partial/Failed Feedback Buttons */}
          <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <Zap className="w-4 h-4 text-brand-500" />
                <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                  Outcome-Ranked Mitigations
                </h3>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">Real Track Record</span>
            </div>

            {rankedFixes.length === 0 ? (
              <div className="text-xs text-slate-400 py-4 text-center">
                No candidate fixes ranked yet.
              </div>
            ) : (
              <div className="space-y-4">
                {rankedFixes.map((fix) => (
                  <div
                    key={fix.rank}
                    className="p-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/40 space-y-2.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center space-x-2">
                        <span className="w-6 h-6 rounded-full bg-brand-600 text-white text-xs font-extrabold flex items-center justify-center shrink-0">
                          #{fix.rank}
                        </span>
                        <h4 className="text-xs font-extrabold text-slate-900 dark:text-white">
                          {fix.label}
                        </h4>
                      </div>
                      <span className="font-mono text-xs font-extrabold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950 px-2 py-0.5 rounded border border-emerald-300 dark:border-emerald-800 shrink-0">
                        Score: {fix.score.toFixed(2)}
                      </span>
                    </div>

                    {/* Transparent Score Inputs Breakdown */}
                    <div className="text-[11px] font-mono text-slate-500 grid grid-cols-2 gap-1 bg-white dark:bg-slate-900/80 p-2.5 rounded-lg border border-slate-200 dark:border-slate-800">
                      <div>Sim: {(fix.similarity * 100).toFixed(0)}%</div>
                      <div>Attempts: {fix.attempts}</div>
                      <div className="text-emerald-600 dark:text-emerald-400">Worked: {fix.worked}</div>
                      <div className="text-amber-600 dark:text-amber-400">Partial: {fix.partial}</div>
                      <div className="text-rose-600 dark:text-rose-400">Failed: {fix.failed}</div>
                      <div className="text-rose-600 dark:text-rose-400">Recent fails: {fix.recent_failures}</div>
                    </div>

                    {fix.last_used_incident_id && (
                      <div className="text-[10px] font-mono text-slate-400">
                        Last used in: {fix.last_used_incident_id}
                      </div>
                    )}

                    {/* The Learning Signal: Feedback buttons */}
                    <div className="pt-2 border-t border-slate-200 dark:border-slate-700/80">
                      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                        Test this fix (Provide Learning Feedback):
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        <button
                          type="button"
                          disabled={submittingFix !== null}
                          onClick={() => handleFeedback(fix.fix_type, 'worked')}
                          className="flex items-center justify-center space-x-1 py-1.5 px-2 rounded-lg bg-emerald-100 hover:bg-emerald-200 dark:bg-emerald-950/80 dark:hover:bg-emerald-900 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 font-bold text-[11px] transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Worked</span>
                        </button>

                        <button
                          type="button"
                          disabled={submittingFix !== null}
                          onClick={() => handleFeedback(fix.fix_type, 'partial')}
                          className="flex items-center justify-center space-x-1 py-1.5 px-2 rounded-lg bg-amber-100 hover:bg-amber-200 dark:bg-amber-950/80 dark:hover:bg-amber-900 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800 font-bold text-[11px] transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>Partial</span>
                        </button>

                        <button
                          type="button"
                          disabled={submittingFix !== null}
                          onClick={() => handleFeedback(fix.fix_type, 'failed')}
                          className="flex items-center justify-center space-x-1 py-1.5 px-2 rounded-lg bg-rose-100 hover:bg-rose-200 dark:bg-rose-950/80 dark:hover:bg-rose-900 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800 font-bold text-[11px] transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          <span>Failed</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Masked Log Snippet */}
          <div className="bg-white dark:bg-[#161F36] p-6 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-3">
            <div className="flex items-center space-x-2">
              <Terminal className="w-4 h-4 text-slate-500" />
              <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                Error Log Telemetry
              </h3>
            </div>
            <pre className="p-3.5 rounded-xl bg-slate-950 text-slate-300 font-mono text-[11px] overflow-x-auto leading-relaxed border border-slate-800">
              {incidentAlert.log_snippet || '(no log snippet attached)'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

export default IncidentDetailView;
