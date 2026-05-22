import React, { useEffect, useState, useCallback } from 'react';
import { listConversations, cancelConversation, resumeConversation, createConversation } from '../../api/client';
import { Conversation, Provider } from '../../types';
import { Plus, MessageSquare, XCircle, Play, Loader2, ChevronDown } from 'lucide-react';

const PROVIDERS: { name: Provider; label: string; color: string }[] = [
  { name: 'groq', label: 'Groq Llama 3.3 (Free)', color: 'bg-orange-100 text-orange-700' },
  { name: 'openai', label: 'OpenAI GPT-4.1', color: 'bg-green-100 text-green-700' },
  { name: 'anthropic', label: 'Claude Sonnet', color: 'bg-purple-100 text-purple-700' },
  { name: 'gemini', label: 'Gemini 2.0 Flash', color: 'bg-blue-100 text-blue-700' },
];

interface Props {
  selectedConversation: Conversation | null;
  onSelect: (conv: Conversation) => void;
  onNew: (conv: Conversation) => void;
  currentProvider: Provider;
  currentModel: string;
  onProviderChange: (provider: Provider, model: string) => void;
}

export const ConversationSidebar: React.FC<Props> = ({
  selectedConversation, onSelect, onNew, currentProvider, currentModel, onProviderChange,
}) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [showProvider, setShowProvider] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await listConversations();
      setConversations(data);
    } catch { /* silently ignore */ }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const handleNew = async () => {
    setLoading(true);
    try {
      const conv = await createConversation(currentProvider, currentModel);
      setConversations(prev => [conv, ...prev]);
      onNew(conv);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async (e: React.MouseEvent, conv: Conversation) => {
    e.stopPropagation();
    const updated = await cancelConversation(conv.session_id);
    setConversations(prev => prev.map(c => c.session_id === conv.session_id ? updated : c));
    if (selectedConversation?.session_id === conv.session_id) onSelect(updated);
  };

  const handleResume = async (e: React.MouseEvent, conv: Conversation) => {
    e.stopPropagation();
    const updated = await resumeConversation(conv.session_id);
    setConversations(prev => prev.map(c => c.session_id === conv.session_id ? updated : c));
    if (selectedConversation?.session_id === conv.session_id) onSelect(updated);
  };

  const selectedProvider = PROVIDERS.find(p => p.name === currentProvider)!;

  return (
    <div className="flex flex-col h-full bg-gray-900 text-gray-100 w-72 flex-shrink-0">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-semibold text-white mb-3">LLM Chat</h1>

        {/* Provider selector */}
        <div className="relative">
          <button
            onClick={() => setShowProvider(!showProvider)}
            className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-gray-800 text-sm hover:bg-gray-700 transition-colors"
          >
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${selectedProvider.color}`}>
              {selectedProvider.label}
            </span>
            <ChevronDown size={14} className={`transition-transform ${showProvider ? 'rotate-180' : ''}`} />
          </button>
          {showProvider && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-gray-800 rounded-lg shadow-xl z-10 overflow-hidden">
              {PROVIDERS.map(p => (
                <button
                  key={p.name}
                  onClick={() => { onProviderChange(p.name, ''); setShowProvider(false); }}
                  className="w-full flex items-center px-3 py-2.5 hover:bg-gray-700 text-sm transition-colors"
                >
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${p.color}`}>{p.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* New conversation button */}
        <button
          onClick={handleNew}
          disabled={loading}
          className="mt-3 w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          New Conversation
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto p-2">
        {conversations.length === 0 && (
          <p className="text-gray-500 text-xs text-center mt-8">No conversations yet</p>
        )}
        {conversations.map(conv => {
          const isSelected = selectedConversation?.session_id === conv.session_id;
          const isCancelled = conv.status === 'cancelled';
          return (
            <div
              key={conv.id}
              onClick={() => onSelect(conv)}
              className={`group flex items-start gap-2 p-3 rounded-lg mb-1 cursor-pointer transition-colors ${
                isSelected ? 'bg-gray-700' : 'hover:bg-gray-800'
              } ${isCancelled ? 'opacity-60' : ''}`}
            >
              <MessageSquare size={14} className="text-gray-400 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-200 truncate">
                  {conv.title || 'New Conversation'}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-gray-500">{conv.provider}</span>
                  {isCancelled && (
                    <span className="text-xs bg-amber-900/50 text-amber-400 px-1.5 py-0.5 rounded">cancelled</span>
                  )}
                  <span className="text-xs text-gray-600">{conv.message_count} msgs</span>
                </div>
              </div>
              {/* Action buttons */}
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                {isCancelled ? (
                  <button
                    onClick={(e) => handleResume(e, conv)}
                    title="Resume"
                    className="p-1 rounded hover:bg-green-800 text-green-400"
                  >
                    <Play size={12} />
                  </button>
                ) : (
                  <button
                    onClick={(e) => handleCancel(e, conv)}
                    title="Cancel"
                    className="p-1 rounded hover:bg-red-900 text-red-400"
                  >
                    <XCircle size={12} />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
