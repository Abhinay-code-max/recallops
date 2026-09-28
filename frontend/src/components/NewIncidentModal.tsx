import React, { useState, useEffect } from 'react';
import {
  X,
  AlertOctagon,
  Sparkles,
  Zap,
  Terminal,
  Server,
  Layers,
  FileText,
} from 'lucide-react';
import { Alert, DemoAlertOut, Severity } from '../types';
import { api } from '../services/api';

interface NewIncidentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (alert: Alert) => Promise<void>;
  isLoading: boolean;
}

export const NewIncidentModal: React.FC<NewIncidentModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}) => {
  const [demoAlerts, setDemoAlerts] = useState<DemoAlertOut[]>([]);
  const [selectedDemoId, setSelectedDemoId] = useState<string>('');

  // Alert fields
  const [title, setTitle] = useState('');
  const [service, setService] = useState('');
  const [severity, setSeverity] = useState<Severity>('SEV1');
  const [errorMessage, setErrorMessage] = useState('');
  const [symptoms, setSymptoms] = useState('');
  const [logSnippet, setLogSnippet] = useState('');
  const [deploy, setDeploy] = useState('');
  const [errorSignature, setErrorSignature] = useState('');

  // Load demo alerts when modal opens
  useEffect(() => {
    if (!isOpen) return;

    api.getDemoAlerts()
      .then((demos) => {
        setDemoAlerts(demos);
        if (demos.length > 0 && !title) {
          applyDemoAlert(demos[0]);
        }
      })
      .catch((err) => console.warn('Could not load demo alerts:', err));
  }, [isOpen]);

  const applyDemoAlert = (demo: DemoAlertOut) => {
    setSelectedDemoId(demo.alert_id);
    setTitle(demo.alert.title);
    setService(demo.alert.service);
    setSeverity(demo.alert.severity);
    setErrorMessage(demo.alert.error_message);
    setSymptoms(demo.alert.symptoms || '');
    setLogSnippet(demo.alert.log_snippet || '');
    setDeploy(demo.alert.deploy || '');
    setErrorSignature(demo.alert.error_signature || '');
  };

  const handleDemoSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setSelectedDemoId(val);
    const found = demoAlerts.find((d) => d.alert_id === val);
    if (found) {
      applyDemoAlert(found);
    }
  };

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !service.trim() || !errorMessage.trim() || !logSnippet.trim()) {
      alert('Please fill in title, service, error message, and log snippet.');
      return;
    }

    const alertPayload: Alert = {
      title: title.trim(),
      service: service.trim(),
      severity,
      error_message: errorMessage.trim(),
      symptoms: symptoms.trim() || undefined,
      log_snippet: logSnippet.trim(),
      deploy: deploy.trim() || undefined,
      error_signature: errorSignature.trim() || undefined,
    };

    await onSubmit(alertPayload);
    onClose();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm animate-in fade-in duration-150"
    >
      <div className="bg-white dark:bg-[#161F36] rounded-3xl max-w-xl w-full p-6 shadow-2xl border border-slate-200 dark:border-slate-700 space-y-4 animate-in zoom-in-95 duration-150 transition-colors max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700/80 pb-3">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-xl bg-rose-50 dark:bg-rose-950/80 text-rose-600 dark:text-rose-400 flex items-center justify-center border border-rose-200 dark:border-rose-900">
              <AlertOctagon className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                Dispatch Production Alert
              </h3>
              <p className="text-[11px] text-slate-500 font-medium">
                Submit live or simulated alert to RecallOps Hindsight memory
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-full text-slate-400 hover:text-slate-700 dark:hover:text-white transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Demo Alert Quick Picker */}
        {demoAlerts.length > 0 && (
          <div className="p-3.5 bg-indigo-50/70 dark:bg-indigo-950/50 rounded-2xl border border-indigo-200 dark:border-indigo-900 space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-brand-700 dark:text-brand-300 flex items-center space-x-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Pre-canned Demo Alert (1-Click Capability Test)</span>
              </label>
              <span className="text-[10px] font-mono text-brand-600 dark:text-brand-400">
                {demoAlerts.length} presets
              </span>
            </div>
            <select
              value={selectedDemoId}
              onChange={handleDemoSelect}
              className="w-full px-3 py-2 bg-white dark:bg-slate-900 border border-indigo-200 dark:border-indigo-800 rounded-xl text-xs text-slate-900 dark:text-white font-medium focus:outline-none focus:ring-2 focus:ring-brand-500 cursor-pointer"
            >
              {demoAlerts.map((d) => (
                <option key={d.alert_id} value={d.alert_id}>
                  [{d.target_capability}] {d.title} ({d.alert.service} - {d.alert.severity})
                </option>
              ))}
            </select>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
                Incident Title
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
              />
            </div>

            <div>
              <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
                Severity
              </label>
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white font-bold focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="SEV1">SEV1 (Critical)</option>
                <option value="SEV2">SEV2 (Major)</option>
                <option value="SEV3">SEV3 (Minor)</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
                Affected Service
              </label>
              <input
                type="text"
                value={service}
                onChange={(e) => setService(e.target.value)}
                placeholder="e.g. payments-api, order-worker, search-api..."
                required
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
              />
            </div>

            <div>
              <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
                Recent Deploy Tag (Optional)
              </label>
              <input
                type="text"
                value={deploy}
                onChange={(e) => setDeploy(e.target.value)}
                placeholder="e.g. v2.3.1"
                className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono"
              />
            </div>
          </div>

          <div>
            <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
              Error Message
            </label>
            <input
              type="text"
              value={errorMessage}
              onChange={(e) => setErrorMessage(e.target.value)}
              placeholder="e.g. remaining connection slots are reserved..."
              required
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
              Symptoms / Impact Description
            </label>
            <input
              type="text"
              value={symptoms}
              onChange={(e) => setSymptoms(e.target.value)}
              placeholder="e.g. 5xx rate > 20%, p99 latency > 4s..."
              className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand-500 font-medium"
            />
          </div>

          <div>
            <label className="block font-bold text-slate-700 dark:text-slate-300 mb-1">
              Raw Log Snippet
            </label>
            <textarea
              rows={4}
              value={logSnippet}
              onChange={(e) => setLogSnippet(e.target.value)}
              placeholder="Paste stack trace or server log snippet..."
              required
              className="w-full p-2.5 bg-slate-950 text-slate-300 font-mono text-[11px] border border-slate-800 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200 dark:border-slate-700">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 rounded-xl font-bold transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-5 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-xl font-bold shadow-md transition-all cursor-pointer flex items-center space-x-1.5 disabled:opacity-50"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>{isLoading ? 'Recalling Memory...' : 'Trigger Incident Alert'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default NewIncidentModal;
