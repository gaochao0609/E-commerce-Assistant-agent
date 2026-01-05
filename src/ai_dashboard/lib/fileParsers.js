/*
 * File: lib/fileParsers.js
 * Purpose: Parses spreadsheet buffers into table structures.
 * Flow: reads the first sheet, normalizes headers, and truncates data.
 * Created: 2026-01-05
 */
import XLSX from 'xlsx';

const normalizeHeader = (value, index) => {
  const clean = String(value || '').trim();
  return clean.length > 0 ? clean : `Column ${index + 1}`;
};

export const parseTableFromBuffer = (buffer, limits) => {
  const workbook = XLSX.read(buffer, { type: 'buffer' });
  const sheetName = workbook.SheetNames[0];
  if (!sheetName) {
    return {
      headers: [],
      rows: [],
      rowCount: 0,
      columnCount: 0
    };
  }

  const sheet = workbook.Sheets[sheetName];
  const rawRows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' });
  const headerRow = rawRows[0] || [];
  const headers = headerRow
    .slice(0, limits.maxColumns)
    .map((value, index) => normalizeHeader(value, index));

  const rows = rawRows
    .slice(1, limits.maxRows + 1)
    .map((row) =>
      headers.map((_, index) => {
        const cell = row[index];
        return cell === undefined || cell === null ? '' : String(cell);
      })
    );

  return {
    headers,
    rows,
    rowCount: Math.max(rawRows.length - 1, 0),
    columnCount: headers.length
  };
};
