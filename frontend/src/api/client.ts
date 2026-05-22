const BACKEND = '/api';
const INGESTION = '/metrics';

// ── Conversations ────────────────────────────────────────────────────────────

export async function listConversations(status?: string) {
  const url = status ? `${BACKEND}/conversations?status=${status}` : `${BACKEND}/conversations`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to list conversations: ${res.statusText}`);
  return res.json();
}

export async function createConversation(provider: string, model?: string) {
  const res = await fetch(`${BACKEND}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, model }),
  });
  if (!res.ok) throw new Error(`Failed to create conversation: ${res.statusText}`);
  return res.json();
}

export async function getConversation(sessionId: string) {
  const res = await fetch(`${BACKEND}/conversations/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to get conversation: ${res.statusText}`);
  return res.json();
}

export async function getMessages(sessionId: string) {
  const res = await fetch(`${BACKEND}/conversations/${sessionId}/messages`);
  if (!res.ok) throw new Error(`Failed to get messages: ${res.statusText}`);
  return res.json();
}

export async function cancelConversation(sessionId: string) {
  const res = await fetch(`${BACKEND}/conversations/${sessionId}/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to cancel conversation: ${res.statusText}`);
  return res.json();
}

export async function resumeConversation(sessionId: string) {
  const res = await fetch(`${BACKEND}/conversations/${sessionId}/resume`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to resume conversation: ${res.statusText}`);
  return res.json();
}

export async function listProviders() {
  const res = await fetch(`${BACKEND}/providers`);
  if (!res.ok) throw new Error(`Failed to list providers`);
  return res.json();
}

// ── Streaming chat ────────────────────────────────────────────────────────────

export interface StreamChatOptions {
  message: string;
  session_id?: string;
  provider: string;
  model?: string;
  onDelta: (delta: string) => void;
  onSessionId: (sessionId: string, model: string) => void;
  onDone: (fullContent: string) => void;
  onError: (err: Error) => void;
  signal?: AbortSignal;
}

export async function streamChat(opts: StreamChatOptions) {
  const res = await fetch(`${BACKEND}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: opts.message,
      session_id: opts.session_id,
      provider: opts.provider,
      model: opts.model,
      stream: true,
    }),
    signal: opts.signal,
  });

  if (!res.ok) {
    const text = await res.text();
    opts.onError(new Error(`Chat error ${res.status}: ${text}`));
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6).trim();
      if (data === '[DONE]') return;
      try {
        const parsed = JSON.parse(data);
        if (parsed.type === 'session') opts.onSessionId(parsed.session_id, parsed.model);
        if (parsed.type === 'delta') opts.onDelta(parsed.content);
        if (parsed.type === 'done') opts.onDone(parsed.content);
      } catch { /* ignore parse errors */ }
    }
  }
}

// ── Metrics ───────────────────────────────────────────────────────────────────

export async function getMetricsSummary(window = '1h') {
  const res = await fetch(`${INGESTION}/summary?window=${window}`);
  if (!res.ok) throw new Error('Failed to fetch metrics summary');
  return res.json();
}

export async function getLatencyMetrics(window = '1h') {
  const res = await fetch(`${INGESTION}/latency?window=${window}`);
  if (!res.ok) throw new Error('Failed to fetch latency metrics');
  return res.json();
}

export async function getThroughputMetrics(window = '1h') {
  const res = await fetch(`${INGESTION}/throughput?window=${window}`);
  if (!res.ok) throw new Error('Failed to fetch throughput metrics');
  return res.json();
}

export async function getErrorMetrics(window = '1h') {
  const res = await fetch(`${INGESTION}/errors?window=${window}`);
  if (!res.ok) throw new Error('Failed to fetch error metrics');
  return res.json();
}

export async function getProviderMetrics(window = '24h') {
  const res = await fetch(`${INGESTION}/by-provider?window=${window}`);
  if (!res.ok) throw new Error('Failed to fetch provider metrics');
  return res.json();
}
