/*
 * File: lib/validators.js
 * Purpose: Validates input payloads for chat and upload routes.
 * Flow: enforces size limits and sanitizes chat messages.
 * Created: 2026-01-05
 */

const ALLOWED_ROLES = new Set(['user', 'assistant', 'system']);
const ALLOWED_EXTENSIONS = new Set(['.xlsx', '.xls', '.csv']);

export const sanitizeMessages = (messages, maxChars) => {
  if (!Array.isArray(messages)) {
    return [];
  }

  return messages
    .filter((message) => message && ALLOWED_ROLES.has(message.role))
    .map((message) => {
      const content = String(message.content || '').slice(0, maxChars);
      return { role: message.role, content };
    })
    .slice(-12);
};

export const validateFile = (file, config) => {
  if (!file) {
    return '未选择文件。';
  }

  const maxBytes = config.maxFileSizeMb * 1024 * 1024;
  if (file.size > maxBytes) {
    return `文件超过 ${config.maxFileSizeMb}MB 限制。`;
  }

  if (file.type) {
    if (!config.allowedFileTypes.includes(file.type)) {
      return '不支持的文件类型。';
    }
    return null;
  }

  const filename = String(file.name || '').toLowerCase();
  const extension = filename.includes('.') ? `.${filename.split('.').pop()}` : '';
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    return '不支持的文件类型。';
  }

  return null;
};
