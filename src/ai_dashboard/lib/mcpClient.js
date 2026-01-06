/*
 * File: lib/mcpClient.js
 * Purpose: Minimal MCP Streamable HTTP client for tool calls.
 * Flow: initializes a session, notifies, calls tool, and returns structured output.
 * Created: 2026-01-05
 */

const DEFAULT_PROTOCOL_VERSION = '2025-06-18';
const DEFAULT_TIMEOUT_MS = Number.parseInt(
  process.env.MCP_CLIENT_TIMEOUT_MS || '10000',
  10
);
const DEFAULT_MAX_RETRIES = Number.parseInt(
  process.env.MCP_CLIENT_MAX_RETRIES || '1',
  10
);
const RETRY_DELAY_MS = 400;

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const buildHeaders = (sessionId, protocolVersion) => {
  const headers = {
    Accept: 'application/json',
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

const parseJsonBody = async (response) => {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error('MCP 响应不是有效 JSON。');
  }
};

const sendJsonRpc = async (url, payload, sessionId, protocolVersion) => {
  return requestWithRetry(async () => {
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

  const { response, body } = await sendJsonRpc(url, initPayload);
  if (body?.error) {
    throw new Error(body.error.message || 'MCP 初始化失败。');
  }

  const sessionId =
    response.headers.get('mcp-session-id') ||
    response.headers.get('MCP-Session-Id');
  const protocolVersion =
    body?.result?.protocolVersion || DEFAULT_PROTOCOL_VERSION;

  return { sessionId, protocolVersion };
};

const sendInitialized = async (url, sessionId, protocolVersion) => {
  await requestWithRetry(async () => {
    const payload = {
      jsonrpc: '2.0',
      method: 'notifications/initialized',
      params: {}
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

  const { body } = await sendJsonRpc(url, payload, sessionId, protocolVersion);
  if (body?.error) {
    throw new Error(body.error.message || 'MCP 工具调用失败。');
  }

  return body?.result?.structuredContent ?? null;
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

    await sendInitialized(url, sessionId, protocolVersion);
    return await callTool(url, sessionId, protocolVersion, toolName, args);
  } finally {
    try {
      await terminateSession(url, sessionId, protocolVersion);
    } catch {
      // Ignore termination errors to avoid masking tool call failures.
    }
  }
};
