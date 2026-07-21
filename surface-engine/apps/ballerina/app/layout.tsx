import React from 'react';

export const metadata = {
  title: 'Ballerina - Kinetic Typography',
  description: 'Public Audience Surfaces Suite - Ballerina Kinetic Typography Application',
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
      <body style={{ margin: 0, padding: 0, fontFamily: 'system-ui, -apple-system, sans-serif', backgroundColor: '#0f051d', color: '#faf5ff' }}>
        {children}
      </body>
    </html>
  );
}
