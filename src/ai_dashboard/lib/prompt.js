/*
 * File: lib/prompt.js
 * Purpose: Builds the system prompt with optional data context.
 * Flow: injects table summary and KPI hints for the AI model.
 * Created: 2026-01-05
 */

import { formatMcpSummary } from './mcpMapper.js';

const summarizeTable = (table) => {
  if (!table || table.headers.length === 0) {
    return '当前没有可用的表格数据。';
  }

  const sampleRows = table.rows.slice(0, 3).map((row) => row.join(' | '));

  return [
    `表头: ${table.headers.join(', ')}`,
    `行数: ${table.rowCount}`,
    `示例行: ${sampleRows.join(' || ')}`
  ].join(' ');
};

export const buildSystemPrompt = (config, table, kpis, mcpReport) => {
  const kpiSummary =
    Array.isArray(kpis) && kpis.length > 0
      ? `指标: ${kpis.map((kpi) => `${kpi.label}: ${kpi.value}`).join(', ')}。`
      : '当前没有可用的指标摘要。';

  const tableSummary = summarizeTable(table);
  const mcpSummary = mcpReport?.summary ? formatMcpSummary(mcpReport.summary) : '';
  const mcpInsights = mcpReport?.insights ? `MCP 洞察: ${mcpReport.insights}` : '';

  return [config.systemPrompt, kpiSummary, tableSummary, mcpSummary, mcpInsights]
    .filter(Boolean)
    .join('\n');
};
