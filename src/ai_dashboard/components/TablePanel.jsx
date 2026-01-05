/*
 * File: components/TablePanel.jsx
 * Purpose: Renders the latest table preview.
 * Flow: shows a truncated table with headers and rows.
 * Created: 2026-01-05
 */

export default function TablePanel({ table }) {
  if (!table) {
    return <div className="empty-state">No table preview yet.</div>;
  }

  return (
    <div className="table-wrapper">
      <div className="panel-title">{table.title}</div>
      <table className="table">
        <thead>
          <tr>
            {table.headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, index) => (
            <tr key={`row-${index}`}>
              {row.map((cell, cellIndex) => (
                <td key={`cell-${index}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
