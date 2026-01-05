/*
 * File: lib/validators.js
 * Purpose: Validates input payloads for chat and upload routes.
 * Flow: enforces size limits and sanitizes chat messages.
 * Created: 2026-01-05
 */

const ALLOWED_ROLES = new Set(['user', 'assistant', 'system']);

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
    return 'No file provided.';
  }

  const maxBytes = config.maxFileSizeMb * 1024 * 1024;
  if (file.size > maxBytes) {
    return `File exceeds ${config.maxFileSizeMb}MB limit.`;
  }

  if (file.type && !config.allowedFileTypes.includes(file.type)) {
    return 'Unsupported file type.';
  }

  return null;
};
