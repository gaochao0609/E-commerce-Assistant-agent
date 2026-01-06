/*
 * File: app/api/upload/route.js
 * Purpose: Accepts spreadsheet uploads and returns metadata.
 * Flow: validates input, stores file, parses table, returns counts.
 * Created: 2026-01-05
 */
import { getRuntimeConfig } from '../../../lib/config.js';
import { parseTableFromBuffer } from '../../../lib/fileParsers.js';
import { callMcpTool } from '../../../lib/mcpClient.js';
import { saveUpload } from '../../../lib/storage.js';
import { validateFile } from '../../../lib/validators.js';
import { logger } from '../../../lib/logger.js';

export const runtime = 'nodejs';

export async function POST(request) {
  try {
    const config = await getRuntimeConfig();
    const formData = await request.formData();
    const file = formData.get('file');

    if (!file || typeof file.arrayBuffer !== 'function') {
      return Response.json({ error: '请上传文件。' }, { status: 400 });
    }

    const validationError = validateFile(file, config);
    if (validationError) {
      return Response.json({ error: validationError }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    const table = parseTableFromBuffer(buffer, config);
    const metadata = await saveUpload(buffer, { name: file.name, type: file.type });

    if (!process.env.MCP_SERVER_URL) {
      return Response.json({
        uploadId: metadata.id,
        filename: metadata.filename,
        rowCount: table.rowCount,
        columnCount: table.columnCount,
        createdAt: metadata.createdAt,
        persisted: false
      });
    }

    const persisted = await callMcpTool(
      process.env.MCP_SERVER_URL,
      'save_upload_table',
      {
        filename: metadata.filename,
        headers: table.headers,
        rows: table.rows,
        row_count: table.rowCount,
        column_count: table.columnCount
      }
    );

    return Response.json({
      uploadId: persisted?.id || metadata.id,
      filename: persisted?.filename || metadata.filename,
      rowCount: table.rowCount,
      columnCount: table.columnCount,
      createdAt: persisted?.created_at || metadata.createdAt,
      persisted: Boolean(persisted)
    });
  } catch (error) {
    logger.error('Upload failed.', error);
    return Response.json({ error: '上传失败。' }, { status: 500 });
  }
}
