export type Provider = 'openai' | 'anthropic' | 'gemini' | 'groq';

export interface Conversation {
  id: string;
  session_id: string;
  title: string | null;
  provider: Provider;
  model: string;
  status: 'active' | 'cancelled' | 'completed';
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  sequence_number: number;
  created_at: string;
}

export interface MetricsSummary {
  window: string;
  total_requests: number;
  error_count: number;
  error_rate: number;
  avg_latency_ms: number;
  p99_latency_ms: number;
  total_tokens: number;
}

export interface LatencyDataPoint {
  timestamp: string;
  latency_ms: number;
  provider: Provider;
}

export interface ThroughputDataPoint {
  bucket: string;
  count: number;
}

export interface ProviderStat {
  provider: Provider;
  requests: number;
  avg_latency_ms: number;
  total_tokens: number;
  errors: number;
}
