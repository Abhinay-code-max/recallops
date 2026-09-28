/**
 * RecallOps API Service
 * Directly communicates with the RecallOps FastAPI backend according to docs/API_CONTRACT.md
 */

import {
  Alert,
  AlertResponse,
  ChatRequest,
  ChatResponse,
  CompareRequest,
  CompareResponse,
  DemoAlertOut,
  FeedbackRequest,
  FeedbackResponse,
  HealthResponse,
  IncidentDetail,
  IncidentSummary,
  InsightsResponse,
  MetricsResponse,
  ResetResponse,
  ResolveRequest,
  ResolveResponse,
  SeedResponse,
  BriefingSections,
} from '../types';

const API_BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000').replace(/\/$/, '');

export interface BriefingStreamCallbacks {
  onToken?: (text: string) => void;
  onSections?: (sections: BriefingSections) => void;
  onDone?: (citedIncidentIds: string[]) => void;
  onError?: (error: string) => void;
}

class RecallOpsApi {
  public baseUrl: string;

  constructor() {
    this.baseUrl = API_BASE;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...((options?.headers as Record<string, string>) || {}),
    };

    if (options?.body && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(url, {
      ...options,
      headers,
    });

    if (!res.ok) {
      let errorMsg = `HTTP ${res.status}: ${res.statusText}`;
      try {
        const errorData = await res.json();
        if (errorData?.detail?.error?.message) {
          errorMsg = errorData.detail.error.message;
        } else if (errorData?.detail) {
          errorMsg = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
        } else if (errorData?.error?.message) {
          errorMsg = errorData.error.message;
        }
      } catch {
        // use fallback errorMsg
      }
      throw new Error(errorMsg);
    }

    return res.json() as Promise<T>;
  }

  // GET /health
  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
  }

  // POST /seed
  async seed(): Promise<SeedResponse> {
    return this.request<SeedResponse>('/seed', { method: 'POST' });
  }

  // POST /reset
  async reset(): Promise<ResetResponse> {
    return this.request<ResetResponse>('/reset', { method: 'POST' });
  }

  // GET /demo-alerts
  async getDemoAlerts(): Promise<DemoAlertOut[]> {
    return this.request<DemoAlertOut[]>('/demo-alerts');
  }

  // POST /alert
  async postAlert(alert: Alert): Promise<AlertResponse> {
    return this.request<AlertResponse>('/alert', {
      method: 'POST',
      body: JSON.stringify(alert),
    });
  }

  // GET /incidents
  async getIncidents(): Promise<IncidentSummary[]> {
    return this.request<IncidentSummary[]>('/incidents');
  }

  // GET /incidents/{id}
  async getIncident(id: string): Promise<IncidentDetail> {
    return this.request<IncidentDetail>(`/incidents/${encodeURIComponent(id)}`);
  }

  // POST /feedback
  async postFeedback(payload: FeedbackRequest): Promise<FeedbackResponse> {
    return this.request<FeedbackResponse>('/feedback', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // POST /resolve
  async resolveIncident(payload: ResolveRequest): Promise<ResolveResponse> {
    return this.request<ResolveResponse>('/resolve', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // POST /chat
  async sendChat(payload: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // POST /compare
  async compare(payload: CompareRequest): Promise<CompareResponse> {
    return this.request<CompareResponse>('/compare', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // GET /insights
  async getInsights(): Promise<InsightsResponse> {
    return this.request<InsightsResponse>('/insights');
  }

  // GET /metrics
  async getMetrics(): Promise<MetricsResponse> {
    return this.request<MetricsResponse>('/metrics');
  }

  // GET /incidents/{incident_id}/briefing/stream (SSE)
  streamBriefing(
    streamUrlOrIncidentId: string,
    callbacks: BriefingStreamCallbacks
  ): () => void {
    const path = streamUrlOrIncidentId.startsWith('/')
      ? streamUrlOrIncidentId
      : `/incidents/${encodeURIComponent(streamUrlOrIncidentId)}/briefing/stream`;
    const fullUrl = `${this.baseUrl}${path}`;

    const eventSource = new EventSource(fullUrl);

    eventSource.addEventListener('token', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (data.text) {
          callbacks.onToken?.(data.text);
        }
      } catch (err) {
        console.error('Error parsing token SSE event:', err);
      }
    });

    eventSource.addEventListener('sections', (event: MessageEvent) => {
      try {
        const sections = JSON.parse(event.data) as BriefingSections;
        callbacks.onSections?.(sections);
      } catch (err) {
        console.error('Error parsing sections SSE event:', err);
      }
    });

    eventSource.addEventListener('done', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        callbacks.onDone?.(data.cited_incident_ids || []);
      } catch (err) {
        console.error('Error parsing done SSE event:', err);
      }
      eventSource.close();
    });

    eventSource.addEventListener('error', (event: MessageEvent | Event) => {
      let errMsg = 'Connection to briefing stream failed.';
      if ('data' in event && event.data) {
        try {
          const parsed = JSON.parse(event.data);
          errMsg = parsed.message || errMsg;
        } catch {
          errMsg = String(event.data);
        }
      }
      callbacks.onError?.(errMsg);
      eventSource.close();
    });

    // Return cleanup function to abort stream
    return () => {
      eventSource.close();
    };
  }
}

export const api = new RecallOpsApi();
