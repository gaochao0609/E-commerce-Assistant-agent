/*
 * File: components/Dashboard.jsx
 * Purpose: Orchestrates chat, uploads, and insights panels for the UI.
 * Flow: uploads files, sends chat prompts, and renders streamed data.
 * Created: 2026-01-05
 */
'use client';

import { useMemo, useState } from 'react';
import { useChat } from 'ai/react';
import ChatPanel from './ChatPanel';
import FileUpload from './FileUpload';
import InsightsPanel from './InsightsPanel';

const initialMessages = [
  {
    role: 'assistant',
    content:
      'Share a metric question or upload a spreadsheet. I will summarize KPIs, charts, and prepare a report.'
  }
];

export default function Dashboard() {
  const [uploadMeta, setUploadMeta] = useState(null);
  const [uploadError, setUploadError] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  const { messages, input, handleInputChange, handleSubmit, isLoading, data } =
    useChat({
      api: '/api/chat',
      initialMessages,
      body: { uploadId: uploadMeta?.uploadId ?? null }
    });

  const latestData = useMemo(() => {
    if (!data || data.length === 0) {
      return { tables: [], charts: [], kpis: [], report: null };
    }
    return data[data.length - 1];
  }, [data]);

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
    } catch (error) {
      setUploadError(error.message || 'Upload failed.');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <main>
      <div className="app-shell">
        <header className="header">
          <span className="tag">Internal Ops</span>
          <h1>Operations AI Assistant</h1>
          <p>Ask for metrics, upload spreadsheets, and generate reports.</p>
        </header>
        <section className="dashboard-grid">
          <div className="panel fade-in">
            <ChatPanel
              messages={messages}
              input={input}
              onInputChange={handleInputChange}
              onSubmit={handleSubmit}
              isLoading={isLoading}
            />
          </div>
          <div className="panel fade-in">
            <FileUpload
              uploadMeta={uploadMeta}
              uploadError={uploadError}
              isUploading={isUploading}
              onUpload={handleFileUpload}
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
