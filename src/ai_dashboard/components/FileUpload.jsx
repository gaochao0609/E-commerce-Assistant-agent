/*
 * File: components/FileUpload.jsx
 * Purpose: Handles file upload interactions for spreadsheet context.
 * Flow: validates selection and triggers the upload callback.
 * Created: 2026-01-05
 */
'use client';

import { useRef } from 'react';

export default function FileUpload({ uploadMeta, uploadError, isUploading, onUpload }) {
  const inputRef = useRef(null);

  const handleChange = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      onUpload(file);
    }
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  };

  return (
    <div className="panel-section">
      <div className="panel-title">
        <span>Data Upload</span>
        <span className="tag">Excel/CSV</span>
      </div>
      <div className="file-card">
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          onChange={handleChange}
          disabled={isUploading}
        />
        <p>{isUploading ? 'Uploading file...' : 'Choose a spreadsheet to add context.'}</p>
        {uploadMeta ? (
          <div>
            <strong>{uploadMeta.filename}</strong>
            <div>
              Rows: {uploadMeta.rowCount} | Columns: {uploadMeta.columnCount}
            </div>
          </div>
        ) : null}
        {uploadError ? <div className="error-text">{uploadError}</div> : null}
      </div>
    </div>
  );
}
