/*
 * File: app/api/upload/route.js
 * Purpose: Accepts spreadsheet uploads and returns metadata.
 * Flow: validates input, stores file, parses table, returns counts.
 * Created: 2026-01-05
 */
import { getRuntimeConfig } from '../../../lib/config.js';
import { parseTableFromBuffer } from '../../../lib/fileParsers.js';
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
      return Response.json({ error: 'File is required.' }, { status: 400 });
    }

    const validationError = validateFile(file, config);
    if (validationError) {
      return Response.json({ error: validationError }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    const metadata = await saveUpload(buffer, { name: file.name, type: file.type });
    const table = parseTableFromBuffer(buffer, config);

    return Response.json({
      uploadId: metadata.id,
      filename: metadata.filename,
      rowCount: table.rowCount,
      columnCount: table.columnCount
    });
  } catch (error) {
    logger.error('Upload failed.', error);
    return Response.json({ error: 'Upload failed.' }, { status: 500 });
  }
}
