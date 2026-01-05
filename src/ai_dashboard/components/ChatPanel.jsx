/*
 * File: components/ChatPanel.jsx
 * Purpose: Renders the chat transcript and input form.
 * Flow: displays messages and relays input submissions.
 * Created: 2026-01-05
 */

const renderMessage = (message, index) => {
  const roleClass = message.role === 'user' ? 'user' : 'assistant';
  return (
    <div className={`message ${roleClass}`} key={`${message.role}-${index}`}>
      {message.content}
    </div>
  );
};

export default function ChatPanel({ messages, input, onInputChange, onSubmit, isLoading }) {
  const visibleMessages = messages.filter((message) => message.role !== 'system');

  return (
    <div className="panel-section">
      <div className="panel-title">
        <span>Conversation</span>
        <span className="tag">Streaming</span>
      </div>
      <div className="chat-window">
        {visibleMessages.length === 0
          ? 'Start a conversation to see responses here.'
          : visibleMessages.map(renderMessage)}
      </div>
      <form className="input-row" onSubmit={onSubmit}>
        <textarea
          placeholder="Ask for KPIs, a report, or a chart."
          value={input}
          onChange={onInputChange}
        />
        <div className="button-row">
          <button className="button" type="submit" disabled={isLoading}>
            {isLoading ? 'Working...' : 'Send request'}
          </button>
        </div>
      </form>
    </div>
  );
}
