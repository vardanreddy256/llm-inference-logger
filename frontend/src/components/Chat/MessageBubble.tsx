import React from 'react';
import { Message } from '../../types';

interface Props {
  message: Message | { role: 'user' | 'assistant'; content: string; id?: string };
  isStreaming?: boolean;
}

export const MessageBubble: React.FC<Props> = ({ message, isStreaming }) => {
  const isUser = message.role === 'user';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap shadow-sm ${
          isUser
            ? 'bg-indigo-600 text-white rounded-br-sm'
            : 'bg-white text-gray-800 border border-gray-100 rounded-bl-sm'
        }`}
      >
        {message.content}
        {isStreaming && (
          <span className="inline-block ml-1 animate-pulse text-indigo-300">▍</span>
        )}
      </div>
    </div>
  );
};
