import React from 'react';

export const metadata = {
  title: 'Tryptich - React Canvas Carousel',
  description: 'Public Audience Surfaces Suite - Tryptich React Canvas Carousel Application',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body style={{ margin: 0, padding: 0, fontFamily: 'system-ui, -apple-system, sans-serif', backgroundColor: '#09090b', color: '#f4f4f5' }}>
        {children}
      </body>
    </html>
  );
}
