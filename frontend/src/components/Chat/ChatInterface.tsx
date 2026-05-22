import React, { useState, useEffect, useRef, useCallback } from 'react';
import { MessageBubble } from './MessageBubble';
import { ChatInput } from './ChatInput';
import { streamChat, getMessages } from '../../api/client';
import { Message, Conversation, Provider } from '../../types';
import { Bot, AlertTriangle } from 'lucide-react';

interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface Props {
  conversation: Conversation | null;
  provider: Provider;
  model: string;
  onConversationCreated: (sessionId: string) => void;
}

export const ChatInterface: React.FC<Props> = ({ conversation, provider, model, onConversationCreated }) => {
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string | undefined>(conversation?.session_id);

  // Load messages when conversation changes
  useEffect(() => {
    sessionIdRef.current = conversation?.session_id;
    if (!conversation) {
      setMessages([]);
      return;
    }
    getMessages(conversation.session_id)
      .then((msgs: Message[]) => {
        setMessages(msgs.map(m => ({ id: m.id, role: m.role as 'user' | 'assistant', content: m.content })));
      })
      .catch(() => setMessages([]));
  }, [conversation?.session_id]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleSend = useCallback(async (text: string) => {
    if (conversation?.status === 'cancelled') {
      setError('This conversation is cancelled. Resume it first.');
      return;
    }
    setError(null);
    const userMsg: LocalMessage = { id: crypto.randomUUID(), role: 'user', content: text };
    setMessages(prev => [...prev, userMsg]);
    setStreamingContent('');
    setIsStreaming(true);

    abortRef.current = new AbortController();

    await streamChat({
      message: text,
      session_id: sessionIdRef.current,
      provider,
      model,
      signal: abortRef.current.signal,
      onSessionId: (sid, _model) => {
        if (!sessionIdRef.current) {
          sessionIdRef.current = sid;
          onConversationCreated(sid);
        }
      },
      onDelta: (delta) => {
        setStreamingContent(prev => prev + delta);
      },
      onDone: (full) => {
        setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: full }]);
        setStreamingContent('');
        setIsStreaming(false);
      },
      onError: (err) => {
        if (err.name !== 'AbortError') {
          setError(err.message);
        }
        setStreamingContent('');
        setIsStreaming(false);
      },
    });
  }, [conversation, provider, model, onConversationCreated]);

  const handleStopStreaming = () => {
    abortRef.current?.abort();
    if (streamingContent) {
      setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'assistant', content: streamingContent + ' [stopped]' }]);
    }
    setStreamingContent('');
    setIsStreaming(false);
  };

  const isCancelled = conversation?.status === 'cancelled';

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 gap-3">
            <Bot size={48} className="text-indigo-300" />
            <p className="text-sm">Start a new conversation below</p>
            <p className="text-xs text-gray-300">Using {provider} / {model}</p>
          </div>
        )}
        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isStreaming && streamingContent && (
          <MessageBubble
            message={{ role: 'assistant', content: streamingContent }}
            isStreaming
          />
        )}
        {error && (
          <div className="flex items-center gap-2 text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-4">
            <AlertTriangle size={16} />
            {error}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      {isCancelled ? (
        <div className="p-4 border-t border-gray-100 bg-amber-50 text-amber-700 text-sm text-center">
          This conversation is cancelled. Resume it from the sidebar to continue.
        </div>
      ) : (
        <ChatInput
          onSend={handleSend}
          onCancel={handleStopStreaming}
          isStreaming={isStreaming}
        />
      )}
    </div>
  );
};
