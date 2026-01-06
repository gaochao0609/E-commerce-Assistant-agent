/*
 * File: app/api/chat/route.js
 * Purpose: Streams AI responses with optional table/chart/report metadata.
 * Flow: validates input, loads upload context, calls AI, streams data.
 * Created: 2026-01-05
 */
import fs from 'fs/promises';
import { streamText, StreamData, StreamingTextResponse, formatStreamPart } from 'ai';
import { openai } from '@ai-sdk/openai';
import { getRuntimeConfig } from '../../../lib/config.js';
import { parseTableFromBuffer } from '../../../lib/fileParsers.js';
import { buildCharts, buildKpis } from '../../../lib/metrics.js';
import { callMcpTool } from '../../../lib/mcpClient.js';
import { mapMcpReportToArtifacts } from '../../../lib/mcpMapper.js';
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
    const config = await getRuntimeConfig();

    const payload = await request.json();
    const messages = sanitizeMessages(payload?.messages, config.maxInputChars);

    if (messages.length === 0) {
      return Response.json({ error: '请输入问题内容。' }, { status: 400 });
    }

    const hasOpenAI = Boolean(process.env.OPENAI_API_KEY);
    const hasMcp = Boolean(process.env.MCP_SERVER_URL);

    if (!hasOpenAI && !hasMcp) {
      return Response.json(
        { error: '未配置 OPENAI_API_KEY 或 MCP_SERVER_URL。' },
        { status: 500 }
      );
    }

    if (hasOpenAI) {
      ensureProvider(config.provider);
    }

    let table = null;
    let uploadKpis = [];
    let uploadCharts = [];
    let report = null;
    let mcpReport = null;
    let mcpArtifacts = { tables: [], charts: [], kpis: [] };

    if (payload?.uploadId) {
      const upload = await getUpload(payload.uploadId);
      if (!upload) {
        return Response.json({ error: '未找到上传文件。' }, { status: 404 });
      }

      const buffer = await fs.readFile(upload.filePath);
      table = parseTableFromBuffer(buffer, config);
      uploadKpis = buildKpis(table);
      uploadCharts = buildCharts(table, config.chartType);

      if (table.headers.length > 0 && shouldGenerateReport(messages)) {
        const reportBuffer = createReportBuffer(table, config.reportFormat);
        report = await saveReport(reportBuffer, config.reportFormat);
      }
    }

    if (process.env.MCP_SERVER_URL) {
      try {
        const focus = messages[messages.length - 1]?.content || null;
        const mcpResult = await callMcpTool(
          process.env.MCP_SERVER_URL,
          'generate_dashboard_insights',
          {
            focus,
            window_days: config.mcpWindowDays,
            top_n: config.mcpTopN
          }
        );

        mcpReport = mcpResult?.report || null;
        mcpArtifacts = mapMcpReportToArtifacts(mcpReport, config.chartType);
      } catch (error) {
        logger.warn('MCP tool call failed.', error);
      }
    }

    const combinedKpis = [...uploadKpis, ...(mcpArtifacts.kpis || [])];
    const combinedTables = [];
    const combinedCharts = [];

    if (table && table.headers.length > 0) {
      combinedTables.push({
        title: '上传数据',
        headers: table.headers,
        rows: table.rows.slice(0, 10)
      });
      combinedCharts.push(...uploadCharts);
    }

    combinedTables.push(...(mcpArtifacts.tables || []));
    combinedCharts.push(...(mcpArtifacts.charts || []));

    const data = new StreamData();

    data.append({
      tables: combinedTables,
      charts: combinedCharts,
      kpis: combinedKpis,
      report: report
        ? {
            id: report.id,
            filename: report.filename
          }
          : null
    });

    data.close();

    if (!hasOpenAI) {
      const fallbackMessage = mcpReport?.insights
        ? `已获取 MCP 洞察：${mcpReport.insights}`
        : mcpReport
          ? 'MCP 已返回数据，请查看右侧指标与表格。'
          : 'MCP 暂无可用数据，请检查 MCP 服务配置。';
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(
            encoder.encode(formatStreamPart('text', fallbackMessage))
          );
          controller.enqueue(
            encoder.encode(
              formatStreamPart('finish_message', { finishReason: 'stop' })
            )
          );
          controller.close();
        }
      });

      return new StreamingTextResponse(stream, {}, data);
    }

    const summaryTable =
      table ||
      (mcpArtifacts.tables[0]
        ? {
            headers: mcpArtifacts.tables[0].headers,
            rows: mcpArtifacts.tables[0].rows,
            rowCount: mcpArtifacts.tables[0].rows.length,
            columnCount: mcpArtifacts.tables[0].headers.length
          }
        : null);

    const system = buildSystemPrompt(config, summaryTable, combinedKpis, mcpReport);
    const model = openai(config.model);
    const result = await streamText({
      model,
      system,
      messages,
      temperature: 0.2
    });

    return result.toDataStreamResponse({ data });
  } catch (error) {
    logger.error('Chat request failed.', error);
    return Response.json({ error: '对话请求失败。' }, { status: 500 });
  }
}
