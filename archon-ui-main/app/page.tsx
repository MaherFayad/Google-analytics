import Link from 'next/link'

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
      <div className="container mx-auto px-4 py-16">
        <div className="max-w-4xl mx-auto text-center">
          {/* Header */}
          <h1 className="text-5xl font-bold text-gray-900 dark:text-white mb-6">
            GA4 Analytics SaaS
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-300 mb-12">
            AI-Powered Google Analytics Chat & Report Generator
          </p>

          {/* Features Grid */}
          <div className="grid md:grid-cols-2 gap-6 mb-12">
            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md">
              <div className="text-3xl mb-3">💬</div>
              <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-white">
                Conversational Analytics
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                Natural language queries → Structured reports
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md">
              <div className="text-3xl mb-3">🤖</div>
              <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-white">
                Multi-Agent AI
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                Specialized agents for data fetching, analysis, and reporting
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md">
              <div className="text-3xl mb-3">⚡</div>
              <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-white">
                Real-time Streaming
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                Server-Sent Events for progressive report generation
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md">
              <div className="text-3xl mb-3">🔒</div>
              <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-white">
                Multi-Tenant SaaS
              </h3>
              <p className="text-gray-600 dark:text-gray-400">
                Secure tenant isolation with Row-Level Security
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/auth/signin"
              className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg shadow-md transition-colors"
            >
              Get Started
            </Link>
            <Link
              href="/dashboard"
              className="px-8 py-3 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-900 dark:text-white font-semibold rounded-lg shadow-md transition-colors"
            >
              Open Dashboard
            </Link>
          </div>

          {/* Status */}
          <div className="mt-12 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
            <p className="text-green-800 dark:text-green-200 font-medium">
              ✅ Frontend is running successfully!
            </p>
            <p className="text-sm text-green-600 dark:text-green-400 mt-1">
              Docker test environment • Port 3000
            </p>
          </div>

          {/* Tech Stack */}
          <div className="mt-12 text-sm text-gray-500 dark:text-gray-400">
            <p className="mb-2">Built with:</p>
            <div className="flex flex-wrap justify-center gap-3">
              <span className="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded">Next.js 14</span>
              <span className="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded">FastAPI</span>
              <span className="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded">Pydantic-AI</span>
              <span className="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded">PostgreSQL + pgvector</span>
              <span className="px-3 py-1 bg-gray-200 dark:bg-gray-700 rounded">Redis</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

