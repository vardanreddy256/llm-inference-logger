import React, { useState, useCallback } from 'react';
import { ConversationSidebar } from './components/Sidebar/ConversationSidebar';
import { ChatInterface } from './components/Chat/ChatInterface';
import { MetricsDashboard } from './components/Dashboard/MetricsDashboard';
import { Conversation, Provider } from './types';
import { listConversations } from './api/client';
import { BarChart2, MessageSquare } from 'lucide-react';

type View = 'chat' | 'dashboard';

const DEFAULT_MODELS: Record<Provider, string> = {
  openai: 'gpt-4.1',
  anthropic: 'claude-sonnet-4-5',
  gemini: 'gemini-2.0-flash',
  groq: 'llama-3.3-70b-versatile',
};

export default function App() {
  const [view, setView] = useState<View>('chat');
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [provider, setProvider] = useState<Provider>('openai');
  const [model, setModel] = useState<string>(DEFAULT_MODELS['openai']);

  const handleProviderChange = (p: Provider, m: string) => {
    setProvider(p);
    setModel(m || DEFAULT_MODELS[p]);
  };

  const handleConversationCreated = useCallback(async (sessionId: string) => {
    // Fetch the newly created conversation and select it
    try {
      const conversations = await listConversations();
      const found = conversations.find((c: Conversation) => c.session_id === sessionId);
      if (found) setSelectedConversation(found);
    } catch { /* ignore */ }
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-gray-100 font-sans">
      {/* Sidebar */}
      <ConversationSidebar
        selectedConversation={selectedConversation}
        onSelect={setSelectedConversation}
        onNew={setSelectedConversation}
        currentProvider={provider}
        currentModel={model}
        onProviderChange={handleProviderChange}
      />

      {/* Main area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar */}
        <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shadow-sm">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-gray-800">
              {selectedConversation?.title ?? (view === 'dashboard' ? 'Inference Dashboard' : 'New Conversation')}
            </h2>
            {selectedConversation && (
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                selectedConversation.status === 'active' ? 'bg-green-100 text-green-700' :
                selectedConversation.status === 'cancelled' ? 'bg-amber-100 text-amber-700' :
                'bg-gray-100 text-gray-600'
              }`}>
                {selectedConversation.status}
              </span>
            )}
          </div>
          <nav className="flex items-center bg-gray-100 rounded-lg p-1 gap-1">
            <button
              onClick={() => setView('chat')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                view === 'chat' ? 'bg-white text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <MessageSquare size={13} />
              Chat
            </button>
            <button
              onClick={() => setView('dashboard')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                view === 'dashboard' ? 'bg-white text-indigo-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <BarChart2 size={13} />
              Dashboard
            </button>
          </nav>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-hidden">
          {view === 'chat' ? (
            <ChatInterface
              conversation={selectedConversation}
              provider={provider}
              model={model}
              onConversationCreated={handleConversationCreated}
            />
          ) : (
            <MetricsDashboard />
          )}
        </main>
      </div>
    </div>
  );
}
