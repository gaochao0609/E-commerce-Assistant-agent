/*
 * File: lib/metrics.js
 * Purpose: Derives KPI and chart data from parsed tables.
 * Flow: scans numeric columns and builds simple aggregates.
 * Created: 2026-01-05
 */

const toNumber = (value) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

export const buildKpis = (table) => {
  if (!table || table.headers.length === 0) {
    return [];
  }

  const numericValues = table.rows
    .flatMap((row) => row.map((cell) => toNumber(cell)))
    .filter((value) => value !== null);

  const total = numericValues.reduce((sum, value) => sum + value, 0);

  return [
    { label: '行数', value: table.rowCount },
    { label: '列数', value: table.columnCount },
    { label: '数值单元格', value: numericValues.length },
    { label: '数值合计', value: total.toFixed(2) }
  ];
};

export const buildCharts = (table, chartType) => {
  if (!table || table.headers.length < 2) {
    return [];
  }

  const labels = [];
  const values = [];

  for (const row of table.rows.slice(0, 12)) {
    const label = row[0];
    const numeric = toNumber(row[1]);
    if (numeric === null) {
      continue;
    }
    labels.push(String(label || `Item ${labels.length + 1}`));
    values.push(numeric);
  }

  if (values.length === 0) {
    return [];
  }

  return [
    {
      title: `按 ${table.headers[0]} 统计的 ${table.headers[1]}`,
      type: chartType,
      labels,
      values
    }
  ];
};
