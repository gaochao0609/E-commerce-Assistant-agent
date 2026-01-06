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

const resolveWindowRange = (messages, fallback) => {
  const lastUser = [...messages].reverse().find((message) => message.role === 'user');
  const text = lastUser?.content ? String(lastUser.content).trim() : '';
  if (!text) {
    return { start: null, end: null, windowDays: fallback };
  }
  const normalized = text.replace(/\s+/g, '');
  const pad2 = (value) => String(value).padStart(2, '0');
  const toIsoDate = (date) =>
    `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  const addDays = (date, offset) => {
    const next = new Date(date);
    next.setDate(next.getDate() + offset);
    return next;
  };
  const startOfWeek = (date) => {
    const next = new Date(date);
    const day = next.getDay();
    const diff = (day + 6) % 7;
    next.setDate(next.getDate() - diff);
    return next;
  };
  const startOfMonth = (date) => new Date(date.getFullYear(), date.getMonth(), 1);
  const endOfMonth = (date) => new Date(date.getFullYear(), date.getMonth() + 1, 0);

  const today = new Date();
  const yesterday = addDays(today, -1);

  if (/(今天|今日|当天|本日)/.test(normalized)) {
    const iso = toIsoDate(today);
    return { start: iso, end: iso, windowDays: null };
  }
  if (/(昨天|昨日)/.test(normalized)) {
    const iso = toIsoDate(yesterday);
    return { start: iso, end: iso, windowDays: null };
  }
  if (/(前天)/.test(normalized)) {
    const iso = toIsoDate(addDays(today, -2));
    return { start: iso, end: iso, windowDays: null };
  }
  if (/(上周|上一周|上星期|上礼拜)/.test(normalized)) {
    const start = addDays(startOfWeek(today), -7);
    const end = addDays(startOfWeek(today), -1);
    return { start: toIsoDate(start), end: toIsoDate(end), windowDays: null };
  }
  if (/(本周|这周|本星期|本礼拜)/.test(normalized)) {
    return {
      start: toIsoDate(startOfWeek(today)),
      end: toIsoDate(today),
      windowDays: null
    };
  }
  if (/(上月|上个月|上一个月)/.test(normalized)) {
    const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const end = new Date(today.getFullYear(), today.getMonth(), 0);
    return { start: toIsoDate(start), end: toIsoDate(end), windowDays: null };
  }
  if (/(本月|这个月)/.test(normalized)) {
    return {
      start: toIsoDate(startOfMonth(today)),
      end: toIsoDate(today),
      windowDays: null
    };
  }
  const dayMatch = normalized.match(/(\d{1,3})天/);
  if (dayMatch) {
    const days = Number.parseInt(dayMatch[1], 10);
    if (Number.isFinite(days) && days > 0) {
      const start = addDays(today, -(days - 1));
      return { start: toIsoDate(start), end: toIsoDate(today), windowDays: null };
    }
  }
  if (/(一周|最近一周|近一周|最近7天|近7天|过去7天|七天)/.test(normalized)) {
    const start = addDays(today, -6);
    return { start: toIsoDate(start), end: toIsoDate(today), windowDays: null };
  }
  if (/(两周|最近14天|近14天|过去14天|十四天)/.test(normalized)) {
    const start = addDays(today, -13);
    return { start: toIsoDate(start), end: toIsoDate(today), windowDays: null };
  }
  if (/(一月|一个月|最近30天|近30天|过去30天|30天)/.test(normalized)) {
    const start = addDays(today, -29);
    return { start: toIsoDate(start), end: toIsoDate(today), windowDays: null };
  }
  return { start: null, end: null, windowDays: fallback };
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
      if (upload) {
        const buffer = await fs.readFile(upload.filePath);
        table = parseTableFromBuffer(buffer, config);
      } else if (process.env.MCP_SERVER_URL) {
        let persisted;
        try {
          persisted = await callMcpTool(
            process.env.MCP_SERVER_URL,
            'get_upload_table',
            { upload_id: payload.uploadId }
          );
        } catch (error) {
          logger.error('MCP tool call failed.', error);
          return Response.json(
            { error: 'MCP 调用失败，请检查 MCP 服务。' },
            { status: 502 }
          );
        }
        if (!persisted) {
          return Response.json({ error: '未找到上传文件。' }, { status: 404 });
        }
        table = {
          headers: persisted.headers || [],
          rows: persisted.rows || [],
          rowCount:
            persisted.row_count ??
            persisted.rowCount ??
            (persisted.rows ? persisted.rows.length : 0),
          columnCount:
            persisted.column_count ??
            persisted.columnCount ??
            (persisted.headers ? persisted.headers.length : 0)
        };
      } else {
        return Response.json({ error: '未找到上传文件。' }, { status: 404 });
      }

      uploadKpis = buildKpis(table);
      uploadCharts = buildCharts(table, config.chartType);

      if (table.headers.length > 0 && shouldGenerateReport(messages)) {
        const reportBuffer = createReportBuffer(table, config.reportFormat);
        report = await saveReport(reportBuffer, config.reportFormat);
      }
    }

    if (process.env.MCP_SERVER_URL) {
      const focus = messages[messages.length - 1]?.content || null;
      const windowRange = resolveWindowRange(messages, config.mcpWindowDays);
      let mcpResult;
      try {
        mcpResult = await callMcpTool(
          process.env.MCP_SERVER_URL,
          'generate_dashboard_insights',
          {
            focus,
            start: windowRange.start || undefined,
            end: windowRange.end || undefined,
            window_days: windowRange.windowDays,
            top_n: config.mcpTopN
          }
        );
      } catch (error) {
        logger.error('MCP tool call failed.', error);
        return Response.json(
          { error: 'MCP 调用失败，请检查 MCP 服务。' },
          { status: 502 }
        );
      }

      mcpReport = mcpResult?.report || null;
      mcpArtifacts = mapMcpReportToArtifacts(mcpReport, config.chartType);
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
    const temperature = /^gpt-5/i.test(config.model) ? 1 : 0.2;
    const result = await streamText({
      model,
      system,
      messages,
      ...(temperature !== undefined ? { temperature } : {})
    });

    return result.toDataStreamResponse({ data });
  } catch (error) {
    logger.error('Chat request failed.', error);
    return Response.json({ error: '对话请求失败。' }, { status: 500 });
  }
}
