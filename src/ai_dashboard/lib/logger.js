/*
 * File: lib/logger.js
 * Purpose: Minimal logger wrapper for consistent server logs.
 * Flow: formats messages with timestamps and levels.
 * Created: 2026-01-05
 */

const formatMessage = (level, message) => {
  const timestamp = new Date().toISOString();
  return `[${timestamp}] [${level}] ${message}`;
};

export const logger = {
  info(message, meta) {
    if (meta) {
      console.log(formatMessage('INFO', message), meta);
      return;
    }
    console.log(formatMessage('INFO', message));
  },
  warn(message, meta) {
    if (meta) {
      console.warn(formatMessage('WARN', message), meta);
      return;
    }
    console.warn(formatMessage('WARN', message));
  },
  error(message, meta) {
    if (meta) {
      console.error(formatMessage('ERROR', message), meta);
      return;
    }
    console.error(formatMessage('ERROR', message));
  }
};
