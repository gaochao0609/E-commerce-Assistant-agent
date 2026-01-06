/*
 * File: app/api/uploads/[id]/route.js
 * Purpose: Deletes persisted upload records.
 * Flow: calls MCP tool and returns status.
 * Created: 2026-01-06
 */
import { callMcpTool } from '../../../../lib/mcpClient.js';
import { logger } from '../../../../lib/logger.js';

export const runtime = 'nodejs';

export async function DELETE(_request, { params }) {
  try {
    if (!process.env.MCP_SERVER_URL) {
      return Response.json({ error: '未配置 MCP_SERVER_URL。' }, { status: 500 });
    }

    if (!params?.id) {
      return Response.json({ error: '缺少上传记录 ID。' }, { status: 400 });
    }

    await callMcpTool(
      process.env.MCP_SERVER_URL,
      'delete_upload_table',
      { upload_id: params.id }
    );

    return Response.json({ ok: true });
  } catch (error) {
    logger.error('Failed to delete upload.', error);
    return Response.json({ error: '删除上传记录失败。' }, { status: 500 });
  }
}
