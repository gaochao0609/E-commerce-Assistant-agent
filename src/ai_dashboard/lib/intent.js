/*
 * File: lib/intent.js
 * Purpose: Derives report and chart intents from chat messages.
 * Flow: scans the latest user message for request keywords.
 * Created: 2026-01-05
 */

const REPORT_KEYWORDS = [
  'report',
  'download',
  'export',
  'csv',
  'xlsx',
  '报告',
  '下载',
  '导出'
];

export const shouldGenerateReport = (messages) => {
  if (!Array.isArray(messages)) {
    return false;
  }

  const lastUser = [...messages].reverse().find((message) => message.role === 'user');
  if (!lastUser) {
    return false;
  }

  const content = String(lastUser.content || '').toLowerCase();
  return REPORT_KEYWORDS.some((keyword) => content.includes(keyword));
};
