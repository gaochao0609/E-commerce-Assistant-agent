/*
 * File: app/api/report/[id]/route.js
 * Purpose: Serves generated report files for download.
 * Flow: loads report metadata and streams the file content.
 * Created: 2026-01-05
 */
import fs from 'fs/promises';
import { getReport } from '../../../../lib/storage.js';
import { logger } from '../../../../lib/logger.js';

export const runtime = 'nodejs';

export async function GET(_request, { params }) {
  try {
    const report = await getReport(params.id);
    if (!report) {
      return new Response('Report not found.', { status: 404 });
    }

    const fileBuffer = await fs.readFile(report.filePath);

    return new Response(fileBuffer, {
      headers: {
        'Content-Type': report.mimeType,
        'Content-Disposition': `attachment; filename="${report.filename}"`
      }
    });
  } catch (error) {
    logger.error('Report download failed.', error);
    return new Response('Report download failed.', { status: 500 });
  }
}
