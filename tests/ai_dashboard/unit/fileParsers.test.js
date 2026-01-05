/*
 * File: tests/ai_dashboard/unit/fileParsers.test.js
 * Purpose: Verifies spreadsheet parsing behavior.
 * Flow: creates an in-memory workbook and asserts parsed output.
 * Created: 2026-01-05
 */
import { describe, expect, it } from 'vitest';
import XLSX from 'xlsx';
import { parseTableFromBuffer } from 'ai-dashboard/lib/fileParsers.js';

const createWorkbookBuffer = () => {
  const workbook = XLSX.utils.book_new();
  const worksheet = XLSX.utils.aoa_to_sheet([
    ['Name', 'Value'],
    ['Alpha', 10],
    ['Beta', 20]
  ]);
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Sheet1');
  return XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' });
};

describe('parseTableFromBuffer', () => {
  it('parses headers and rows within limits', () => {
    const buffer = createWorkbookBuffer();
    const table = parseTableFromBuffer(buffer, { maxRows: 10, maxColumns: 5 });

    expect(table.headers).toEqual(['Name', 'Value']);
    expect(table.rows).toEqual([
      ['Alpha', '10'],
      ['Beta', '20']
    ]);
    expect(table.rowCount).toBe(2);
    expect(table.columnCount).toBe(2);
  });
});
