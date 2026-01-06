/*
 * File: tests/ai_dashboard/unit/metrics.test.js
 * Purpose: Ensures KPI and chart derivation logic stays consistent.
 * Flow: feeds a small table and inspects KPI values and chart output.
 * Created: 2026-01-05
 */
import { describe, expect, it } from 'vitest';
import { buildCharts, buildKpis } from 'ai-dashboard/lib/metrics.js';

const table = {
  headers: ['Item', 'Amount'],
  rows: [
    ['A', '12'],
    ['B', '18']
  ],
  rowCount: 2,
  columnCount: 2
};

describe('buildKpis', () => {
  it('produces KPI values from numeric cells', () => {
    const kpis = buildKpis(table);
    const rowKpi = kpis.find((kpi) => kpi.label === '行数');
    const sumKpi = kpis.find((kpi) => kpi.label === '数值合计');

    expect(rowKpi.value).toBe(2);
    expect(sumKpi.value).toBe('30.00');
  });
});

describe('buildCharts', () => {
  it('builds a chart based on the first numeric column', () => {
    const charts = buildCharts(table, 'bar');

    expect(charts).toHaveLength(1);
    expect(charts[0].labels).toEqual(['A', 'B']);
    expect(charts[0].values).toEqual([12, 18]);
  });
});
