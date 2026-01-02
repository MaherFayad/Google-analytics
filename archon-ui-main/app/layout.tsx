import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { RootProviders } from '@/providers/RootProviders'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'GA4 Analytics SaaS',
  description: 'AI-Powered Google Analytics Chat & Report Generator',
  viewport: 'width=device-width, initial-scale=1',
  themeColor: '#2563eb',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className} suppressHydrationWarning>
        <RootProviders>
          {children}
        </RootProviders>
      </body>
    </html>
  )
}

