/*
 * File: lib/reporting.js
 * Purpose: Generates report files from table data.
 * Flow: builds a workbook and returns a buffer in the configured format.
 * Created: 2026-01-05
 */
import * as XLSX from 'xlsx/xlsx.mjs';

export const createReportBuffer = (table, format) => {
  if (!table || table.headers.length === 0) {
    return Buffer.from('');
  }

  const data = [table.headers, ...table.rows];
  const worksheet = XLSX.utils.aoa_to_sheet(data);
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, '报告');

  if (format === 'csv') {
    const csv = XLSX.write(workbook, { bookType: 'csv', type: 'string' });
    return Buffer.from(csv, 'utf-8');
  }

  return XLSX.write(workbook, { bookType: 'xlsx', type: 'buffer' });
};
