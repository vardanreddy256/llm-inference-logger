import React, { useEffect, useState, useCallback } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { getMetricsSummary, getLatencyMetrics, getThroughputMetrics, getProviderMetrics } from '../../api/client';
import { MetricsSummary, LatencyDataPoint, ThroughputDataPoint, ProviderStat } from '../../types';
import { Activity, Zap, AlertTriangle, Hash, RefreshCw } from 'lucide-react';

const WINDOWS = ['1h', '6h', '24h', '7d'];

const PROVIDER_COLORS: Record<string, string> = {
  openai: '#10b981',
  anthropic: '#8b5cf6',
  gemini: '#3b82f6',
};

const StatCard: React.FC<{ icon: React.ReactNode; label: string; value: string; sub?: string; color?: string }> = ({
  icon, label, value, sub, color = 'text-indigo-600',
}) => (
  <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
    <div className="flex items-center gap-2 text-gray-500 text-xs mb-2">
      <span className={color}>{icon}</span>
      {label}
    </div>
    <p className={`text-2xl font-bold ${color}`}>{value}</p>
    {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
  </div>
);

export const MetricsDashboard: React.FC = () => {
  const [window, setWindow] = useState('1h');
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [latency, setLatency] = useState<LatencyDataPoint[]>([]);
  const [throughput, setThroughput] = useState<ThroughputDataPoint[]>([]);
  const [providerStats, setProviderStats] = useState<ProviderStat[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, l, t, p] = await Promise.allSettled([
        getMetricsSummary(window),
        getLatencyMetrics(window),
        getThroughputMetrics(window),
        getProviderMetrics(window),
      ]);
      if (s.status === 'fulfilled') setSummary(s.value);
      if (l.status === 'fulfilled') setLatency(l.value);
      if (t.status === 'fulfilled') setThroughput(t.value);
      if (p.status === 'fulfilled') setProviderStats(p.value);
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  }, [window]);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  const fmtLatency = (v: number) => v > 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`;
  const fmtTime = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="h-full overflow-y-auto bg-gray-50 p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-800">Inference Dashboard</h2>
        <div className="flex items-center gap-3">
          <div className="flex bg-white border border-gray-200 rounded-lg overflow-hidden">
            {WINDOWS.map(w => (
              <button
                key={w}
                onClick={() => setWindow(w)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  window === w ? 'bg-indigo-600 text-white' : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                {w}
              </button>
            ))}
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="p-2 rounded-lg border border-gray-200 bg-white text-gray-500 hover:text-indigo-600 transition-colors"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {lastUpdated && (
        <p className="text-xs text-gray-400 mb-4">
          Last updated: {lastUpdated.toLocaleTimeString()}
        </p>
      )}

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={<Hash size={14} />}
            label="Total Requests"
            value={summary.total_requests.toLocaleString()}
            color="text-indigo-600"
          />
          <StatCard
            icon={<Zap size={14} />}
            label="Avg Latency"
            value={fmtLatency(summary.avg_latency_ms)}
            sub={`p99: ${fmtLatency(summary.p99_latency_ms)}`}
            color="text-emerald-600"
          />
          <StatCard
            icon={<AlertTriangle size={14} />}
            label="Error Rate"
            value={`${summary.error_rate}%`}
            sub={`${summary.error_count} errors`}
            color={summary.error_rate > 5 ? 'text-red-600' : 'text-amber-600'}
          />
          <StatCard
            icon={<Activity size={14} />}
            label="Total Tokens"
            value={summary.total_tokens.toLocaleString()}
            color="text-violet-600"
          />
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Latency trend */}
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Latency Over Time</h3>
          {latency.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={latency}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="timestamp" tickFormatter={fmtTime} tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={v => `${Math.round(v)}ms`} tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(v: number) => [fmtLatency(v), 'Latency']}
                  labelFormatter={fmtTime}
                />
                {['openai', 'anthropic', 'gemini'].map(p => (
                  <Line
                    key={p}
                    type="monotone"
                    dataKey="latency_ms"
                    data={latency.filter(d => d.provider === p)}
                    stroke={PROVIDER_COLORS[p]}
                    dot={false}
                    name={p}
                    strokeWidth={2}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-gray-400 text-sm">No data yet</div>
          )}
        </div>

        {/* Throughput */}
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Requests per Minute</h3>
          {throughput.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={throughput}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="bucket" tickFormatter={fmtTime} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip labelFormatter={fmtTime} />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Requests" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-gray-400 text-sm">No data yet</div>
          )}
        </div>
      </div>

      {/* Provider breakdown */}
      {providerStats.length > 0 && (
        <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Provider Breakdown</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 text-xs border-b border-gray-100">
                  <th className="pb-2 pr-4">Provider</th>
                  <th className="pb-2 pr-4">Requests</th>
                  <th className="pb-2 pr-4">Avg Latency</th>
                  <th className="pb-2 pr-4">Total Tokens</th>
                  <th className="pb-2">Errors</th>
                </tr>
              </thead>
              <tbody>
                {providerStats.map(stat => (
                  <tr key={stat.provider} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2 pr-4">
                      <span
                        className="inline-block w-2 h-2 rounded-full mr-2"
                        style={{ background: PROVIDER_COLORS[stat.provider] ?? '#999' }}
                      />
                      {stat.provider}
                    </td>
                    <td className="py-2 pr-4 text-gray-700">{stat.requests.toLocaleString()}</td>
                    <td className="py-2 pr-4 text-gray-700">{fmtLatency(stat.avg_latency_ms)}</td>
                    <td className="py-2 pr-4 text-gray-700">{stat.total_tokens.toLocaleString()}</td>
                    <td className="py-2 text-red-500">{stat.errors}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
