/*
 * File: components/KpiPanel.jsx
 * Purpose: Displays KPI cards derived from the latest dataset.
 * Flow: renders a compact grid of KPI values.
 * Created: 2026-01-05
 */

export default function KpiPanel({ kpis }) {
  if (!kpis || kpis.length === 0) {
    return <div className="empty-state">暂无指标数据。</div>;
  }

  return (
    <div className="kpi-grid">
      {kpis.map((kpi) => (
        <div className="kpi" key={kpi.label}>
          <div className="kpi-label">{kpi.label}</div>
          <div className="kpi-value">{kpi.value}</div>
        </div>
      ))}
    </div>
  );
}
