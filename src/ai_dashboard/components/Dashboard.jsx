/*
 * File: components/Dashboard.jsx
 * Purpose: Shell component for the AI dashboard layout.
 * Flow: renders the header and placeholder panels until features are wired.
 * Created: 2026-01-05
 */
export default function Dashboard() {
  return (
    <main>
      <div className="app-shell">
        <header className="header">
          <span className="tag">Internal Ops</span>
          <h1>Operations AI Assistant</h1>
          <p>Ask for metrics, upload spreadsheets, and generate reports.</p>
        </header>
        <section className="dashboard-grid">
          <div className="panel">Chat panel coming soon.</div>
          <div className="panel">Insights panel coming soon.</div>
        </section>
      </div>
    </main>
  );
}
