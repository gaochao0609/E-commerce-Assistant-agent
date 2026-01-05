/*
 * File: components/ReportPanel.jsx
 * Purpose: Provides report download actions.
 * Flow: renders a link to the generated report endpoint.
 * Created: 2026-01-05
 */

export default function ReportPanel({ report }) {
  if (!report) {
    return (
      <div className="empty-state">
        Ask for a report to generate a downloadable file.
      </div>
    );
  }

  return (
    <div className="download-card">
      <div>
        <strong>Report ready:</strong> {report.filename}
      </div>
      <a className="button secondary" href={`/api/report/${report.id}`}>
        Download report
      </a>
    </div>
  );
}
