/*
 * File: components/FileUpload.jsx
 * Purpose: Handles file upload interactions for spreadsheet context.
 * Flow: validates selection and triggers the upload callback.
 * Created: 2026-01-05
 */
'use client';

import { useMemo, useRef } from 'react';

export default function FileUpload({
  uploadMeta,
  uploadError,
  isUploading,
  onUpload,
  uploads,
  isLoadingUploads,
  onRefreshUploads,
  onSelectUpload,
  onDeleteUpload
}) {
  const inputRef = useRef(null);
  const uploadItems = useMemo(() => (Array.isArray(uploads) ? uploads : []), [uploads]);

  const handleChange = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      onUpload(file);
    }
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  };

  const formatTimestamp = (value) => {
    if (!value) {
      return '未知时间';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString();
  };

  return (
    <div className="panel-section">
      <div className="panel-title">
        <span>数据上传</span>
        <span className="tag">Excel/CSV</span>
      </div>
      <div className="file-card">
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          aria-label="上传数据文件"
          onChange={handleChange}
          disabled={isUploading}
        />
        <p>{isUploading ? '正在上传文件...' : '选择表格文件作为上下文。'}</p>
        {uploadMeta ? (
          <div>
            <strong>{uploadMeta.filename}</strong>
            <div>
              行数: {uploadMeta.rowCount} | 列数: {uploadMeta.columnCount}
            </div>
          </div>
        ) : null}
        {uploadError ? <div className="error-text">{uploadError}</div> : null}
      </div>
      <div className="upload-history">
        <div className="panel-title">
          <span>历史上传</span>
          <button
            className="button ghost"
            type="button"
            onClick={onRefreshUploads}
            disabled={isLoadingUploads}
          >
            {isLoadingUploads ? '刷新中...' : '刷新'}
          </button>
        </div>
        {isLoadingUploads ? (
          <div className="empty-state">正在加载上传记录...</div>
        ) : uploadItems.length === 0 ? (
          <div className="empty-state">暂无历史上传记录。</div>
        ) : (
          <div className="upload-list">
            {uploadItems.map((upload) => {
              const isActive = uploadMeta?.uploadId === upload.id;
              return (
                <div className={`upload-item ${isActive ? 'active' : ''}`} key={upload.id}>
                  <div className="upload-main">
                    <div className="upload-name">{upload.filename}</div>
                    <div className="upload-meta">
                      行数: {upload.row_count} | 列数: {upload.column_count} |{' '}
                      {formatTimestamp(upload.created_at)}
                    </div>
                  </div>
                  <div className="upload-actions">
                    <button
                      className="button secondary"
                      type="button"
                      onClick={() => onSelectUpload(upload)}
                    >
                      使用
                    </button>
                    <button
                      className="button ghost danger"
                      type="button"
                      onClick={() => onDeleteUpload(upload.id)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
