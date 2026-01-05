/*
 * File: lib/prompt.js
 * Purpose: Builds the system prompt with optional data context.
 * Flow: injects table summary and KPI hints for the AI model.
 * Created: 2026-01-05
 */

const summarizeTable = (table) => {
  if (!table || table.headers.length === 0) {
    return 'No table data is available.';
  }

  const sampleRows = table.rows.slice(0, 3).map((row) => row.join(' | '));

  return [
    `Headers: ${table.headers.join(', ')}`,
    `Row count: ${table.rowCount}`,
    `Sample rows: ${sampleRows.join(' || ')}`
  ].join(' ');
};

export const buildSystemPrompt = (config, table, kpis) => {
  const kpiSummary = Array.isArray(kpis) && kpis.length > 0
    ? `KPIs: ${kpis.map((kpi) => `${kpi.label}: ${kpi.value}`).join(', ')}.`
    : 'No KPI summary available.';

  const tableSummary = summarizeTable(table);

  return `${config.systemPrompt}\n${kpiSummary}\n${tableSummary}`;
};
