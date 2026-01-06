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
        <span>对话</span>
        <span className="tag">流式</span>
      </div>
      <div className="chat-window">
        {visibleMessages.length === 0
          ? '开始对话后将在此显示回复。'
          : visibleMessages.map(renderMessage)}
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
