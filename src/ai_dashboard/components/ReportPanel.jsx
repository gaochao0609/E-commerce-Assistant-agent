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
        请在对话中请求生成报告。
      </div>
    );
  }

  return (
    <div className="download-card">
      <div>
        <strong>报告已生成:</strong> {report.filename}
      </div>
      <a className="button secondary" href={`/api/report/${report.id}`}>
        下载报告
      </a>
    </div>
  );
}
