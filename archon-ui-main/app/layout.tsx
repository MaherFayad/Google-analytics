import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'GA4 Analytics SaaS',
  description: 'AI-Powered Google Analytics Chat & Report Generator',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}

