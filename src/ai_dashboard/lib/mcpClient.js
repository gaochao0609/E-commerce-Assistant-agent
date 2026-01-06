/*
 * File: lib/mcpClient.js
 * Purpose: Minimal MCP Streamable HTTP client for tool calls.
 * Flow: initializes a session, notifies, calls tool, and returns structured output.
 * Created: 2026-01-05
 */

const DEFAULT_PROTOCOL_VERSION = '2025-06-18';
const DEFAULT_TIMEOUT_MS = Number.parseInt(
  process.env.MCP_CLIENT_TIMEOUT_MS || '30000',
  10
);
const INSIGHTS_TIMEOUT_MS = Number.parseInt(
  process.env.MCP_CLIENT_INSIGHTS_TIMEOUT_MS || '120000',
  10
);
const DEFAULT_MAX_RETRIES = Number.parseInt(
  process.env.MCP_CLIENT_MAX_RETRIES || '1',
  10
);
const RETRY_DELAY_MS = 400;
const DEBUG = ['1', 'true', 'yes'].includes(
  String(process.env.MCP_CLIENT_DEBUG || '').toLowerCase()
);

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const debugLog = (...args) => {
  if (DEBUG) {
    console.log('[mcp-client]', ...args);
  }
};

const buildHeaders = (sessionId, protocolVersion) => {
  const headers = {
    Accept: 'application/json, text/event-stream',
    Connection: 'close',
    'Content-Type': 'application/json'
  };

  if (sessionId) {
    headers['MCP-Session-Id'] = sessionId;
  }
  if (protocolVersion) {
    headers['MCP-Protocol-Version'] = String(protocolVersion);
  }

  return headers;
};

const fetchWithTimeout = async (url, options, timeoutMs) => {
  const controller = new AbortController();
  const timeout =
    Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 10000;
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
};

const requestWithRetry = async (fn) => {
  const maxRetries =
    Number.isFinite(DEFAULT_MAX_RETRIES) && DEFAULT_MAX_RETRIES >= 0
      ? DEFAULT_MAX_RETRIES
      : 0;
  let attempt = 0;
  while (true) {
    try {
      return await fn();
    } catch (error) {
      if (attempt >= maxRetries || error?.name === 'AbortError') {
        throw error;
      }
      await delay(RETRY_DELAY_MS * (attempt + 1));
      attempt += 1;
    }
  }
};

const parseEventStream = (text) => {
  const events = text.split(/\r?\n\r?\n/);
  const parsed = [];
  for (const event of events) {
    const dataLines = event
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart());
    if (dataLines.length === 0) {
      continue;
    }
    const payload = dataLines.join('\n').trim();
    if (!payload || payload === '[DONE]') {
      continue;
    }
    try {
      parsed.push(JSON.parse(payload));
    } catch {
      // keep scanning for the next valid JSON payload
    }
  }
  if (parsed.length === 0) {
    throw new Error('MCP 响应不是有效 JSON。');
  }
  const sessionPayload = parsed.find(
    (item) =>
      item?.result?.sessionId ||
      item?.result?.session_id ||
      item?.result?.session?.id
  );
  return sessionPayload || parsed[parsed.length - 1];
};

const parseJsonBody = async (response) => {
  const text = await response.text();
  if (!text) {
    return null;
  }
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('text/event-stream')) {
    return parseEventStream(text);
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    return parseEventStream(text);
  }
};

const sendJsonRpc = async (
  url,
  payload,
  sessionId,
  protocolVersion,
  timeoutMs
) => {
  return requestWithRetry(async () => {
    const response = await fetchWithTimeout(
      url,
      {
        method: 'POST',
        headers: buildHeaders(sessionId, protocolVersion),
        body: JSON.stringify(payload)
      },
      timeoutMs ?? DEFAULT_TIMEOUT_MS
    );

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`MCP 请求失败 (${response.status}). ${detail}`);
    }

    const body = await parseJsonBody(response);
    return { response, body };
  });
};

const initializeSession = async (url) => {
  const initPayload = {
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: {
      protocolVersion: DEFAULT_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: {
        name: 'ai-dashboard',
        version: '0.1.0'
      }
    }
  };

  const { response, body } = await sendJsonRpc(
    url,
    initPayload,
    null,
    DEFAULT_PROTOCOL_VERSION,
    DEFAULT_TIMEOUT_MS
  );
  debugLog('initialize response', {
    status: response.status,
    contentType: response.headers.get('content-type'),
    sessionHeader: response.headers.get('mcp-session-id'),
    sessionHeaderAlt: response.headers.get('MCP-Session-Id'),
    sessionHeaderAlt2: response.headers.get('MCP-Session-ID'),
    bodyResultSessionId: body?.result?.sessionId,
    bodyResultSessionIdAlt: body?.result?.session_id,
    bodyResultSessionObj: body?.result?.session?.id
  });
  if (body?.error) {
    throw new Error(body.error.message || 'MCP 初始化失败。');
  }

  const sessionId =
    response.headers.get('mcp-session-id') ||
    response.headers.get('MCP-Session-Id') ||
    response.headers.get('MCP-Session-ID') ||
    body?.result?.sessionId ||
    body?.result?.session_id ||
    body?.result?.session?.id ||
    null;
  if (!sessionId) {
    debugLog('initialize: no session id returned; treating as stateless');
  }
  const protocolVersion =
    body?.result?.protocolVersion || DEFAULT_PROTOCOL_VERSION;

  return { sessionId, protocolVersion };
};

const sendInitialized = async (url, sessionId, protocolVersion) => {
  await requestWithRetry(async () => {
    const payload = {
      jsonrpc: '2.0',
      method: 'notifications/initialized'
    };

    const response = await fetchWithTimeout(
      url,
      {
        method: 'POST',
        headers: buildHeaders(sessionId, protocolVersion),
        body: JSON.stringify(payload)
      },
      DEFAULT_TIMEOUT_MS
    );

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`MCP 初始化通知失败 (${response.status}). ${detail}`);
    }
  });
};

const callTool = async (url, sessionId, protocolVersion, toolName, args) => {
  const payload = {
    jsonrpc: '2.0',
    id: 2,
    method: 'tools/call',
    params: {
      name: toolName,
      arguments: args ?? {}
    }
  };

  const { body } = await sendJsonRpc(
    url,
    payload,
    sessionId,
    protocolVersion,
    getToolTimeout(toolName)
  );
  if (body?.error) {
    throw new Error(body.error.message || 'MCP 工具调用失败。');
  }

  return body?.result?.structuredContent ?? null;
};

const getToolTimeout = (toolName) => {
  if (toolName === 'generate_dashboard_insights') {
    return INSIGHTS_TIMEOUT_MS;
  }
  return DEFAULT_TIMEOUT_MS;
};

const terminateSession = async (url, sessionId, protocolVersion) => {
  if (!sessionId) {
    return;
  }

  await fetchWithTimeout(
    url,
    {
      method: 'DELETE',
      headers: buildHeaders(sessionId, protocolVersion)
    },
    DEFAULT_TIMEOUT_MS
  );
};

export const callMcpTool = async (url, toolName, args) => {
  let sessionId;
  let protocolVersion;

  try {
    const session = await initializeSession(url);
    sessionId = session.sessionId;
    protocolVersion = session.protocolVersion;

    if (sessionId) {
      await sendInitialized(url, sessionId, protocolVersion);
    }
    return await callTool(url, sessionId, protocolVersion, toolName, args);
  } finally {
    try {
      await terminateSession(url, sessionId, protocolVersion);
    } catch {
      // Ignore termination errors to avoid masking tool call failures.
    }
  }
};
