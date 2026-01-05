/*
 * File: lib/storage.js
 * Purpose: Handles temporary storage for uploads and generated reports.
 * Flow: persists files under OS temp and stores JSON metadata for lookup.
 * Created: 2026-01-05
 */
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import crypto from 'crypto';

const UPLOAD_DIR = path.join(os.tmpdir(), 'ai-dashboard-uploads');
const REPORT_DIR = path.join(os.tmpdir(), 'ai-dashboard-reports');

const ensureDir = async (dir) => {
  await fs.mkdir(dir, { recursive: true });
};

const safeName = (name) => {
  return name.replace(/[^a-zA-Z0-9._-]/g, '_');
};

const writeMetadata = async (dir, id, metadata) => {
  const metaPath = path.join(dir, `${id}.json`);
  await fs.writeFile(metaPath, JSON.stringify(metadata, null, 2));
};

const readMetadata = async (dir, id) => {
  const metaPath = path.join(dir, `${id}.json`);
  try {
    const raw = await fs.readFile(metaPath, 'utf-8');
    return JSON.parse(raw);
  } catch (error) {
    return null;
  }
};

export const saveUpload = async (buffer, file) => {
  await ensureDir(UPLOAD_DIR);
  const id = crypto.randomUUID();
  const filename = safeName(file.name || 'upload');
  const extension = path.extname(filename) || '.bin';
  const storedName = `${id}${extension}`;
  const filePath = path.join(UPLOAD_DIR, storedName);

  await fs.writeFile(filePath, buffer);

  const metadata = {
    id,
    filePath,
    filename,
    size: buffer.length,
    mimeType: file.type || 'application/octet-stream',
    createdAt: new Date().toISOString()
  };

  await writeMetadata(UPLOAD_DIR, id, metadata);
  return metadata;
};

export const getUpload = async (id) => {
  const metadata = await readMetadata(UPLOAD_DIR, id);
  if (!metadata) {
    return null;
  }
  return metadata;
};

export const saveReport = async (buffer, format) => {
  await ensureDir(REPORT_DIR);
  const id = crypto.randomUUID();
  const extension = format === 'csv' ? '.csv' : '.xlsx';
  const filename = `report-${id}${extension}`;
  const filePath = path.join(REPORT_DIR, filename);
  const mimeType =
    format === 'csv'
      ? 'text/csv'
      : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

  await fs.writeFile(filePath, buffer);

  const metadata = {
    id,
    filePath,
    filename,
    mimeType,
    createdAt: new Date().toISOString()
  };

  await writeMetadata(REPORT_DIR, id, metadata);
  return metadata;
};

export const getReport = async (id) => {
  const metadata = await readMetadata(REPORT_DIR, id);
  if (!metadata) {
    return null;
  }
  return metadata;
};
