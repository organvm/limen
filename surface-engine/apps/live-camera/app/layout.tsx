import React from 'react';

export const metadata = {
  title: 'Live Camera - Broadcast Framework',
  description: 'Public Audience Surfaces Suite - Livestream Broadcast Framework Application',
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
      <body style={{ margin: 0, padding: 0, fontFamily: 'system-ui, -apple-system, sans-serif', backgroundColor: '#09090b', color: '#fafafa' }}>
        {children}
      </body>
    </html>
  );
}
