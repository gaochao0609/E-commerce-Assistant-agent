/*
 * File: components/ChatPanel.jsx
 * Purpose: Renders the chat transcript and input form.
 * Flow: displays messages, animates the latest response, and relays submissions.
 * Created: 2026-01-05
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

const TYPING_INTERVAL_MS = 16;
const TYPING_CHUNK = 3;

const useTypewriter = (text, enabled) => {
  const [displayed, setDisplayed] = useState(enabled ? '' : text);
  const indexRef = useRef(enabled ? 0 : text.length);
  const textRef = useRef(text);

  useEffect(() => {
    textRef.current = text;
    if (!enabled) {
      indexRef.current = text.length;
      setDisplayed(text);
      return;
    }
    if (indexRef.current > text.length) {
      indexRef.current = text.length;
      setDisplayed(text);
    }
  }, [text, enabled]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const timer = setInterval(() => {
      const target = textRef.current;
      const currentLength = indexRef.current;
      if (currentLength >= target.length) {
        return;
      }
      const nextLength = Math.min(currentLength + TYPING_CHUNK, target.length);
      indexRef.current = nextLength;
      setDisplayed(target.slice(0, nextLength));
    }, TYPING_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [enabled]);

  return displayed;
};

const MessageBubble = ({ message, isTyping }) => {
  const roleClass = message.role === 'user' ? 'user' : 'assistant';
  const content = useTypewriter(message.content || '', isTyping);
  return (
    <div className={`message ${roleClass} ${isTyping ? 'typing' : ''}`}>
      {content}
    </div>
  );
};

export default function ChatPanel({
  messages,
  input,
  onInputChange,
  onSubmit,
  isLoading,
  error
}) {
  const visibleMessages = useMemo(
    () => messages.filter((message) => message.role !== 'system'),
    [messages]
  );
  const lastAssistantIndex = useMemo(() => {
    for (let i = visibleMessages.length - 1; i >= 0; i -= 1) {
      if (visibleMessages[i].role === 'assistant') {
        return i;
      }
    }
    return -1;
  }, [visibleMessages]);
  const chatWindowRef = useRef(null);

  useEffect(() => {
    if (!chatWindowRef.current) {
      return;
    }
    chatWindowRef.current.scrollTop = chatWindowRef.current.scrollHeight;
  }, [visibleMessages, isLoading]);

  return (
    <div className="panel-section">
      <div className="panel-title">
        <span>对话</span>
        <span className="tag">流式</span>
      </div>
      {error ? <div className="chat-error error-text">{error}</div> : null}
      <div className="chat-window" ref={chatWindowRef}>
        {visibleMessages.length === 0 ? (
          <div className="empty-state">开始对话后将在此显示回复。</div>
        ) : (
          visibleMessages.map((message, index) => (
            <MessageBubble
              key={`${message.role}-${index}`}
              message={message}
              isTyping={isLoading && message.role === 'assistant' && index === lastAssistantIndex}
            />
          ))
        )}
      </div>
      <form className="input-row" onSubmit={onSubmit}>
        <textarea
          placeholder="请输入指标、报告或图表需求。"
          value={input}
          onChange={onInputChange}
        />
        <div className="button-row">
          <button className="button" type="submit" disabled={isLoading}>
            {isLoading ? '处理中...' : '发送请求'}
          </button>
        </div>
      </form>
    </div>
  );
}
