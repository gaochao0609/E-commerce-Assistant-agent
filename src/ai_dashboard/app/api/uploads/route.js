/*
 * File: app/api/uploads/route.js
 * Purpose: Lists persisted upload records.
 * Flow: calls MCP tool and returns upload summaries.
 * Created: 2026-01-06
 */
import { callMcpTool } from '../../../lib/mcpClient.js';
import { logger } from '../../../lib/logger.js';

export const runtime = 'nodejs';

export async function GET() {
  try {
    if (!process.env.MCP_SERVER_URL) {
      return Response.json({ uploads: [] });
    }

    const result = await callMcpTool(
      process.env.MCP_SERVER_URL,
      'list_upload_tables',
      { limit: 50 }
    );
    return Response.json({ uploads: result?.uploads || [] });
  } catch (error) {
    logger.error('Failed to list uploads.', error);
    return Response.json({ error: '获取上传列表失败。' }, { status: 500 });
  }
}
