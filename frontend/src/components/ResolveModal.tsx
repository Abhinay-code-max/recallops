import React, { useState } from 'react';
import {
  X,
  ShieldCheck,
  CheckCircle2,
  Clock,
  User,
  FileText,
  Sparkles,
  ArrowRight,
} from 'lucide-react';
import { ResolveResponse, Postmortem } from '../types';
import { api } from '../services/api';

export interface ResolveModalProps {
  isOpen: boolean;
  incidentId: string;
  onClose: () => void;
  onResolved: (res: ResolveResponse) => void;
}

export const ResolveModal: React.FC<ResolveModalProps> = ({
  isOpen,
  incidentId,
  onClose,
  onResolved,
}) => {
  const [resolver, setResolver] = useState('');
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [minutesToResolve, setMinutesToResolve] = useState<number | ''>(15);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [postmortemResult, setPostmortemResult] = useState<Postmortem | null>(null);
  const [memoriesStored, setMemoriesStored] = useState<number | null>(null);

  if (!isOpen) return null;

  const handleResolve = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolver.trim()) {
      setError('Please specify the resolver name.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const res = await api.resolveIncident({
        incident_id: incidentId,
        resolver: resolver.trim(),
        resolution_notes: resolutionNotes.trim() || undefined,
        minutes_to_resolve: typeof minutesToResolve === 'number' ? minutesToResolve : undefined,
      });

      setPostmortemResult(res.postmortem);
      setMemoriesStored(res.memories_stored);
      onResolved(res);
    } catch (err: any) {
      setError(err.message || 'Failed to resolve incident');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDone = () => {
    setPostmortemResult(null);
    setMemoriesStored(null);
    setResolver('');
    setResolutionNotes('');
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/75 backdrop-blur-sm animate-in fade-in duration-150"
    >
      <div className="bg-white dark:bg-[#161F36] rounded-3xl max-w-xl w-full p-6 shadow-2xl border border-slate-200 dark:border-slate-700 space-y-5 animate-in zoom-in-95 duration-150 transition-colors max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700/80 pb-3">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-200 dark:border-emerald-900">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                Resolve Incident & Store Postmortem
              </h3>
              <p className="text-[11px] text-slate-500 font-mono">Incident: {incidentId}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full text-slate-400 hover:text-slate-700 dark:hover:text-white transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="p-3 bg-rose-50 dark:bg-rose-950/80 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 rounded-xl text-xs">
            {error}
          </div>
        )}

        {/* Postmortem Result View after successful POST /resolve */}
        {postmortemResult ? (
          <div className="space-y-4">
            <div className="p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-300 dark:border-emerald-800 text-xs space-y-2">
              <div className="flex items-center space-x-2 text-emerald-800 dark:text-emerald-300 font-extrabold text-sm">
                <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                <span>Incident Resolved & Retained in Hindsight!</span>
              </div>
              <p className="text-emerald-700 dark:text-emerald-300 font-medium">
                {memoriesStored} memory item(s) permanently committed to the live knowledge base.
              </p>
            </div>

            <div className="bg-slate-50 dark:bg-slate-900/80 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 text-xs space-y-3">
              <div className="flex items-center space-x-1.5 font-bold text-slate-900 dark:text-white">
                <Sparkles className="w-4 h-4 text-brand-500" />
                <span>Generated Postmortem</span>
              </div>

              <div>
                <strong className="block text-[11px] uppercase tracking-wider text-slate-400">Root Cause:</strong>
                <p className="text-slate-800 dark:text-slate-200 font-medium mt-0.5">{postmortemResult.root_cause}</p>
              </div>

              <div>
                <strong className="block text-[11px] uppercase tracking-wider text-slate-400">Fix Applied:</strong>
                <p className="text-slate-800 dark:text-slate-200 font-medium mt-0.5">{postmortemResult.fix}</p>
              </div>

              {postmortemResult.action_items?.length > 0 && (
                <div>
                  <strong className="block text-[11px] uppercase tracking-wider text-slate-400">Action Items:</strong>
                  <ul className="list-disc list-inside space-y-0.5 text-slate-700 dark:text-slate-300 font-medium mt-0.5">
                    {postmortemResult.action_items.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {postmortemResult.timeline?.length > 0 && (
                <div>
                  <strong className="block text-[11px] uppercase tracking-wider text-slate-400">Timeline:</strong>
                  <div className="space-y-1 font-mono text-[11px] text-slate-600 dark:text-slate-400 mt-1">
                    {postmortemResult.timeline.map((entry, i) => (
                      <div key={i} className="flex space-x-2">
                        {entry.time && <span className="font-bold text-slate-500">{entry.time.split('T')[1] || entry.time}:</span>}
                        <span>{entry.event}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={handleDone}
              className="w-full py-3 bg-brand-600 hover:bg-brand-700 text-white rounded-xl font-bold text-xs shadow-md transition-all cursor-pointer"
            >
              Close & Return to Dashboard
            </button>
          </div>
        ) : (
          /* Resolution Input Form */
          <form onSubmit={handleResolve} className="space-y-4 text-xs">
            <div>
              <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
                Resolver Name (Required)
              </label>
              <input
                type="text"
                value={resolver}
                onChange={(e) => setResolver(e.target.value)}
                placeholder="e.g. Priya Sharma, Alex Rivera..."
                required
                className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
              />
            </div>

            <div>
              <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
                Minutes to Resolve (MTTR)
              </label>
              <input
                type="number"
                min="1"
                value={minutesToResolve}
                onChange={(e) => setMinutesToResolve(e.target.value ? parseInt(e.target.value, 10) : '')}
                className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium font-mono"
              />
            </div>

            <div>
              <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
                Resolution Notes & Fix Details
              </label>
              <textarea
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                rows={3}
                placeholder="Describe how the issue was fixed and any follow-up actions..."
                className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
              />
            </div>

            <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200 dark:border-slate-700">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2.5 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl font-bold text-xs transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-bold text-xs shadow-md transition-all cursor-pointer disabled:opacity-50"
              >
                {isSubmitting ? 'Resolving & Retaining...' : 'Submit Resolution'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default ResolveModal;
