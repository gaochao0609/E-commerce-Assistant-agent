/*
 * File: components/Dashboard.jsx
 * Purpose: Orchestrates chat, uploads, and insights panels for the UI.
 * Flow: uploads files, sends chat prompts, and renders streamed data.
 * Created: 2026-01-05
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
import { useChat } from 'ai/react';
import ChatPanel from './ChatPanel';
import FileUpload from './FileUpload';
import InsightsPanel from './InsightsPanel';

const initialMessages = [
  {
    role: 'assistant',
    content:
      '可以提指标问题或上传表格。我会汇总指标与图表，并准备报告。'
  }
];

export default function Dashboard() {
  const [uploadMeta, setUploadMeta] = useState(null);
  const [uploadError, setUploadError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadList, setUploadList] = useState([]);
  const [isLoadingUploads, setIsLoadingUploads] = useState(false);
  const [chatError, setChatError] = useState('');

  const { messages, input, handleInputChange, handleSubmit, isLoading, data } =
    useChat({
      api: '/api/chat',
      initialMessages,
      body: { uploadId: uploadMeta?.uploadId ?? null },
      onError: (error) => {
        const rawMessage = error?.message || '';
        try {
          const parsed = JSON.parse(rawMessage);
          setChatError(parsed?.error || rawMessage || '对话请求失败。');
        } catch {
          setChatError(rawMessage || '对话请求失败。');
        }
      },
      onFinish: () => {
        setChatError('');
      }
    });

  const latestData = useMemo(() => {
    if (!data || data.length === 0) {
      return { tables: [], charts: [], kpis: [], report: null };
    }
    return data[data.length - 1];
  }, [data]);

  const loadUploads = async () => {
    setIsLoadingUploads(true);
    try {
      const response = await fetch('/api/uploads');
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || 'Failed to load uploads.');
      }
      setUploadList(Array.isArray(payload.uploads) ? payload.uploads : []);
    } catch (error) {
      setUploadError(error.message || 'Failed to load uploads.');
    } finally {
      setIsLoadingUploads(false);
    }
  };

  useEffect(() => {
    loadUploads();
  }, []);

  const handleChatSubmit = (event) => {
    setChatError('');
    handleSubmit(event);
  };

  const handleFileUpload = async (file) => {
    if (!file) {
      return;
    }

    setIsUploading(true);
    setUploadError('');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || 'Upload failed.');
      }

      setUploadMeta(payload);
      await loadUploads();
    } catch (error) {
      setUploadError(error.message || 'Upload failed.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleSelectUpload = (upload) => {
    if (!upload) {
      return;
    }
    setUploadMeta({
      uploadId: upload.id,
      filename: upload.filename,
      rowCount: upload.row_count,
      columnCount: upload.column_count,
      createdAt: upload.created_at,
      persisted: true
    });
  };

  const handleDeleteUpload = async (uploadId) => {
    if (!uploadId) {
      return;
    }
    const confirmed = window.confirm('确认删除该上传记录吗？');
    if (!confirmed) {
      return;
    }
    try {
      const response = await fetch(`/api/uploads/${uploadId}`, { method: 'DELETE' });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || 'Delete failed.');
      }
      if (uploadMeta?.uploadId === uploadId) {
        setUploadMeta(null);
      }
      await loadUploads();
    } catch (error) {
      setUploadError(error.message || 'Delete failed.');
    }
  };

  return (
    <main>
      <div className="app-shell">
        <header className="header">
          <span className="tag">内部运维</span>
          <h1>运维 AI 助手</h1>
          <p>对话查询指标，上传表格，生成报告。</p>
        </header>
        <section className="dashboard-grid">
          <div className="panel fade-in">
            <ChatPanel
              messages={messages}
              input={input}
              onInputChange={handleInputChange}
              onSubmit={handleChatSubmit}
              isLoading={isLoading}
              error={chatError}
            />
          </div>
          <div className="panel fade-in">
            <FileUpload
              uploadMeta={uploadMeta}
              uploadError={uploadError}
              isUploading={isUploading}
              onUpload={handleFileUpload}
              uploads={uploadList}
              isLoadingUploads={isLoadingUploads}
              onRefreshUploads={loadUploads}
              onSelectUpload={handleSelectUpload}
              onDeleteUpload={handleDeleteUpload}
            />
            <InsightsPanel
              kpis={latestData?.kpis || []}
              tables={latestData?.tables || []}
              charts={latestData?.charts || []}
              report={latestData?.report || null}
            />
          </div>
        </section>
      </div>
    </main>
  );
}
