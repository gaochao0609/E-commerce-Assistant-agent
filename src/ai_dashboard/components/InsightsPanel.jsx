/*
 * File: components/InsightsPanel.jsx
 * Purpose: Composes KPI, table, chart, and report views.
 * Flow: selects the latest data objects and renders sub-panels.
 * Created: 2026-01-05
 */
import ChartPanel from './ChartPanel';
import KpiPanel from './KpiPanel';
import ReportPanel from './ReportPanel';
import TablePanel from './TablePanel';

export default function InsightsPanel({ kpis, tables, charts, report }) {
  const table = tables?.[0];
  const chart = charts?.[0];

  return (
    <div className="insights-stack">
      <div className="panel-title">Insights</div>
      <KpiPanel kpis={kpis} />
      <TablePanel table={table} />
      <ChartPanel chart={chart} />
      <ReportPanel report={report} />
    </div>
  );
}
