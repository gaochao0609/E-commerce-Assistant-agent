/*
 * File: app/layout.jsx
 * Purpose: Root layout and font setup for the AI dashboard UI.
 * Flow: loads fonts, applies global classes, and renders the app shell.
 * Created: 2026-01-05
 */
import './globals.css';
import { Space_Grotesk, Fraunces } from 'next/font/google';

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap'
});

const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-display',
  display: 'swap'
});

export const metadata = {
  title: 'Operations AI Assistant',
  description: 'Internal operations assistant for metrics and reports.'
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${fraunces.variable}`}>
      <body>
        {children}
      </body>
    </html>
  );
}
