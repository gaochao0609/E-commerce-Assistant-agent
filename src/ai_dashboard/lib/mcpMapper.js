/*
 * File: lib/mcpMapper.js
 * Purpose: Maps MCP dashboard summaries into UI-ready artifacts.
 * Flow: formats KPI, table, and chart data from MCP report payloads.
 * Created: 2026-01-05
 */

const formatNumber = (value, fractionDigits) => {
  if (!Number.isFinite(value)) {
    return '-';
  }

  const digits = Number.isFinite(fractionDigits) ? fractionDigits : 2;
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format(value);
};

const formatInteger = (value) => {
  if (!Number.isFinite(value)) {
    return '-';
  }

  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: 0
  }).format(value);
};

const formatPercent = (value) => {
  if (!Number.isFinite(value)) {
    return '-';
  }

  return `${(value * 100).toFixed(1)}%`;
};

export const formatMcpSummary = (summary) => {
  if (!summary || !summary.totals) {
    return '';
  }

  const { window, totals } = summary;
  const windowText =
    window?.start && window?.end ? `${window.start} ~ ${window.end}` : '未知窗口';

  return [
    `MCP 摘要: 时间窗口 ${windowText}。`,
    `总销售额 ${formatNumber(totals.revenue)}，总销量 ${formatInteger(totals.units)}，会话 ${formatInteger(totals.sessions)}。`,
    `转化率 ${formatPercent(totals.conversion_rate)}，退款率 ${formatPercent(totals.refund_rate)}。`
  ].join(' ');
};

export const mapMcpReportToArtifacts = (report, chartType) => {
  if (!report || !report.summary) {
    return { kpis: [], tables: [], charts: [] };
  }

  const { summary } = report;
  const totals = summary.totals || {};
  const topProducts = summary.top_products || [];

  const kpis = [
    { label: '总销售额', value: formatNumber(totals.revenue) },
    { label: '总销量', value: formatInteger(totals.units) },
    { label: '会话数', value: formatInteger(totals.sessions) },
    { label: '转化率', value: formatPercent(totals.conversion_rate) },
    { label: '退款率', value: formatPercent(totals.refund_rate) }
  ];

  const tables = [];
  if (topProducts.length > 0) {
    tables.push({
      title: '重点商品表现',
      headers: [
        'ASIN',
        '商品',
        '销售额',
        '销量',
        '会话数',
        '转化率',
        '退款数',
        '购物车占比'
      ],
      rows: topProducts.map((product) => [
        product.asin || '-',
        product.title || '-',
        formatNumber(product.revenue),
        formatInteger(product.units),
        formatInteger(product.sessions),
        formatPercent(product.conversion_rate),
        formatInteger(product.refunds),
        formatPercent(product.buy_box_percentage)
      ])
    });
  }

  const charts = [];
  if (topProducts.length > 0) {
    const labels = [];
    const values = [];

    for (const product of topProducts.slice(0, 10)) {
      labels.push(product.title || product.asin || `商品 ${labels.length + 1}`);
      values.push(Number.isFinite(product.revenue) ? product.revenue : 0);
    }

    charts.push({
      title: '重点商品销售额',
      type: chartType || 'bar',
      labels,
      values
    });
  }

  return { kpis, tables, charts };
};
