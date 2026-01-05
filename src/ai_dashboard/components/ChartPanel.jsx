/*
 * File: components/ChartPanel.jsx
 * Purpose: Displays charts from derived data series.
 * Flow: builds chart datasets and renders with Chart.js.
 * Created: 2026-01-05
 */
'use client';

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend
} from 'chart.js';
import { Bar, Line } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend
);

const buildDataset = (chart) => ({
  labels: chart.labels,
  datasets: [
    {
      label: chart.title,
      data: chart.values,
      backgroundColor: 'rgba(217, 107, 67, 0.6)',
      borderColor: 'rgba(43, 111, 126, 0.8)',
      borderWidth: 2
    }
  ]
});

export default function ChartPanel({ chart }) {
  if (!chart) {
    return <div className="empty-state">No chart data yet.</div>;
  }

  const data = buildDataset(chart);
  const options = {
    responsive: true,
    plugins: {
      legend: { display: false }
    }
  };

  return (
    <div className="chart-wrapper">
      <div className="panel-title">{chart.title}</div>
      {chart.type === 'line' ? (
        <Line data={data} options={options} />
      ) : (
        <Bar data={data} options={options} />
      )}
    </div>
  );
}
