/*
 * File: app/api/chat/route.js
 * Purpose: Streams AI responses with optional table/chart/report metadata.
 * Flow: validates input, loads upload context, calls AI, streams data.
 * Created: 2026-01-05
 */
import fs from 'fs/promises';
import { streamText, StreamData } from 'ai';
import { openai } from '@ai-sdk/openai';
import { getRuntimeConfig } from '../../../lib/config.js';
import { parseTableFromBuffer } from '../../../lib/fileParsers.js';
import { buildCharts, buildKpis } from '../../../lib/metrics.js';
import { buildSystemPrompt } from '../../../lib/prompt.js';
import { createReportBuffer } from '../../../lib/reporting.js';
import { getUpload, saveReport } from '../../../lib/storage.js';
import { shouldGenerateReport } from '../../../lib/intent.js';
import { sanitizeMessages } from '../../../lib/validators.js';
import { logger } from '../../../lib/logger.js';

export const runtime = 'nodejs';

const ensureProvider = (provider) => {
  if (provider !== 'openai') {
    throw new Error(`Unsupported provider: ${provider}`);
  }
};

export async function POST(request) {
  try {
    if (!process.env.OPENAI_API_KEY) {
      return Response.json({ error: 'OPENAI_API_KEY is not configured.' }, { status: 500 });
    }

    const config = await getRuntimeConfig();
    ensureProvider(config.provider);

    const payload = await request.json();
    const messages = sanitizeMessages(payload?.messages, config.maxInputChars);

    if (messages.length === 0) {
      return Response.json({ error: 'Message is required.' }, { status: 400 });
    }

    let table = null;
    let kpis = [];
    let charts = [];
    let report = null;

    if (payload?.uploadId) {
      const upload = await getUpload(payload.uploadId);
      if (!upload) {
        return Response.json({ error: 'Upload not found.' }, { status: 404 });
      }

      const buffer = await fs.readFile(upload.filePath);
      table = parseTableFromBuffer(buffer, config);
      kpis = buildKpis(table);
      charts = buildCharts(table, config.chartType);

      if (table.headers.length > 0 && shouldGenerateReport(messages)) {
        const reportBuffer = createReportBuffer(table, config.reportFormat);
        report = await saveReport(reportBuffer, config.reportFormat);
      }
    }

    const system = buildSystemPrompt(config, table, kpis);
    const model = openai(config.model);
    const result = await streamText({
      model,
      system,
      messages,
      temperature: 0.2
    });

    const data = new StreamData();

    if (table && table.headers.length > 0) {
      data.append({
        tables: [
          {
            title: 'Uploaded Data',
            headers: table.headers,
            rows: table.rows.slice(0, 10)
          }
        ],
        charts,
        kpis,
        report: report
          ? {
              id: report.id,
              filename: report.filename
            }
          : null
      });
    } else {
      data.append({
        tables: [],
        charts: [],
        kpis,
        report: null
      });
    }

    data.close();

    return result.toDataStreamResponse({ data });
  } catch (error) {
    logger.error('Chat request failed.', error);
    return Response.json({ error: 'Chat request failed.' }, { status: 500 });
  }
}
