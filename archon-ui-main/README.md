# GA4 Analytics SaaS - Frontend

AI-powered Google Analytics 4 chat interface with real-time streaming, multi-tenant support, and comprehensive analytics reporting.

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ 
- Backend API running (see parent directory)
- Google OAuth credentials

### Installation

```bash
# Install dependencies
npm install

# Copy environment template
cp env.example .env.local

# Configure .env.local with your credentials
# (See Configuration section below)

# Start development server
npm run dev
```

Or use the quick start script:

**Linux/Mac:**
```bash
./start-frontend.sh
```

**Windows:**
```powershell
.\start-frontend.ps1
```

The application will be available at `http://localhost:3000`

## 📁 Project Structure

```
archon-ui-main/
├── app/                          # Next.js 14 App Router
│   ├── dashboard/                # Main dashboard (protected)
│   ├── analytics/                # Analytics query interface
│   ├── auth/                     # Authentication pages
│   │   ├── signin/              # Google OAuth sign-in
│   │   └── error/               # Auth error handling
│   ├── settings/                 # User settings
│   ├── layout.tsx               # Root layout with providers
│   └── page.tsx                 # Landing page
├── src/
│   ├── components/              # React components
│   │   ├── ga4/                 # GA4-specific components
│   │   │   ├── ChatInterface.tsx       # Main chat UI
│   │   │   ├── ChatLayout.tsx          # Layout with sidebar
│   │   │   ├── HistorySidebar.tsx      # Session history
│   │   │   ├── MetricCard.tsx          # Metric display
│   │   │   ├── ChartRenderer.tsx       # Chart visualization
│   │   │   └── ...
│   │   ├── ui/                  # Reusable UI components
│   │   ├── charts/              # Chart components
│   │   └── errors/              # Error boundaries
│   ├── hooks/                   # Custom React hooks
│   │   ├── useChatStream.ts    # SSE streaming
│   │   ├── useChatSessions.ts  # Session management
│   │   └── useApiClient.ts     # API client
│   ├── lib/                     # Utilities
│   │   ├── api-client.ts       # Axios client with interceptors
│   │   └── utils.ts            # Helper functions
│   ├── contexts/                # React contexts
│   │   └── TenantContext.tsx   # Multi-tenant context
│   ├── providers/               # Provider wrappers
│   │   └── RootProviders.tsx   # App-wide providers
│   └── types/                   # TypeScript types
├── middleware.ts                # Auth middleware
├── next.config.js              # Next.js configuration
├── tailwind.config.js          # Tailwind CSS config
└── tsconfig.json               # TypeScript config
```

## 🔧 Configuration

### Environment Variables

Create `.env.local` from `env.example`:

```env
# Backend API
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_API_URL=http://localhost:8000

# NextAuth
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-secret-here  # Generate: openssl rand -base64 32

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google Analytics API
4. Create OAuth 2.0 credentials
5. Add authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
6. Copy Client ID and Secret to `.env.local`

## 🎯 Features

### ✅ Implemented

- **Authentication**
  - Google OAuth sign-in
  - Protected routes
  - Session management
  - Auto-redirect on auth failure

- **Chat Interface**
  - Real-time SSE streaming
  - Message history
  - Typing indicators
  - Error handling with retry
  - Auto-scroll

- **Chat History**
  - Session management
  - Search and filter
  - Rename sessions
  - Delete sessions
  - Load previous conversations

- **Analytics Reporting**
  - Metric cards with trends
  - Interactive charts (line, bar, pie, area)
  - Confidence indicators
  - Source citations
  - Pattern matching

- **Multi-Tenant**
  - Tenant selector
  - Context switching
  - Isolated data access

- **UI/UX**
  - Responsive design (mobile, tablet, desktop)
  - Dark mode support
  - Loading states
  - Error boundaries
  - Accessibility features

### 🔄 Coming Soon

- CSV/PDF export
- Historical period comparison
- Advanced chart types
- Report sharing
- Admin dashboard
- Usage analytics

## 📖 Documentation

- **[FRONTEND_SETUP.md](./FRONTEND_SETUP.md)** - Detailed setup instructions
- **[TESTING_GUIDE.md](./TESTING_GUIDE.md)** - Comprehensive testing guide
- **[docs/](./docs/)** - Additional documentation

## 🧪 Testing

### Run Tests

```bash
# Type checking
npm run type-check

# Linting
npm run lint

# Build (production)
npm run build
```

### Manual Testing

See [TESTING_GUIDE.md](./TESTING_GUIDE.md) for detailed testing instructions.

### Test Checklist

- [ ] Landing page loads
- [ ] Authentication flow works
- [ ] Dashboard displays correctly
- [ ] Chat sends/receives messages
- [ ] SSE streaming works
- [ ] History sidebar functions
- [ ] Responsive on mobile
- [ ] No console errors

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│         Frontend (Next.js 14)           │
│                                         │
│  ┌─────────────┐      ┌──────────────┐ │
│  │  Dashboard  │◄─────┤ Auth (OAuth) │ │
│  └──────┬──────┘      └──────────────┘ │
│         │                               │
│  ┌──────▼──────────────────────────┐   │
│  │      Chat Interface              │   │
│  │  ┌────────────┐  ┌────────────┐ │   │
│  │  │  History   │  │   Chat     │ │   │
│  │  │  Sidebar   │  │  Messages  │ │   │
│  │  └────────────┘  └────────────┘ │   │
│  └─────────────────────────────────┘   │
│         │                               │
│  ┌──────▼──────────────────────────┐   │
│  │    API Client (Axios + SSE)     │   │
│  └─────────────────────────────────┘   │
└──────────────┬──────────────────────────┘
               │
               │ HTTP/SSE
               │
┌──────────────▼──────────────────────────┐
│      Backend (FastAPI + Pydantic-AI)    │
└─────────────────────────────────────────┘
```

## 🎨 Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: Radix UI + shadcn/ui
- **State Management**: React Query (TanStack Query)
- **Authentication**: NextAuth.js
- **Charts**: Recharts
- **HTTP Client**: Axios
- **Streaming**: Server-Sent Events (SSE)

## 📦 Key Dependencies

```json
{
  "next": "^14.1.0",
  "react": "^18.2.0",
  "next-auth": "^4.24.5",
  "@tanstack/react-query": "^5.17.19",
  "axios": "^1.6.5",
  "recharts": "^2.10.3",
  "tailwindcss": "^3.4.1"
}
```

## 🛠️ Development

### Available Scripts

```bash
# Development server
npm run dev

# Production build
npm run build

# Start production server
npm start

# Type checking
npm run type-check

# Linting
npm run lint

# Generate types from OpenAPI
npm run generate:types
```

### Code Style

- Use TypeScript for all new files
- Follow ESLint rules
- Use Prettier for formatting
- Document components with JSDoc
- Write semantic HTML

### Component Guidelines

1. **Functional Components**: Use function components with hooks
2. **TypeScript**: Define prop interfaces
3. **Error Handling**: Wrap in error boundaries
4. **Loading States**: Show loading indicators
5. **Accessibility**: Add ARIA labels and semantic HTML

## 🐛 Troubleshooting

### Common Issues

**Issue**: "Connection refused" on API calls

**Solution**: 
- Ensure backend is running on `http://localhost:8000`
- Check `NEXT_PUBLIC_API_BASE_URL` in `.env.local`
- Verify CORS configuration in backend

---

**Issue**: Authentication not working

**Solution**:
- Verify Google OAuth credentials
- Check authorized redirect URIs
- Ensure `NEXTAUTH_SECRET` is set
- Clear cookies and try again

---

**Issue**: SSE streaming not working

**Solution**:
- Check browser supports EventSource
- Verify backend SSE endpoint
- Check for proxy/firewall blocking
- Try in different browser

---

**Issue**: Charts not rendering

**Solution**:
- Check console for Recharts errors
- Verify chart data format
- Check chart config schema
- Ensure data is not empty

## 📝 Contributing

1. Create a feature branch
2. Make your changes
3. Run tests and linting
4. Submit a pull request

## 📄 License

[Your License Here]

## 🤝 Support

For issues or questions:
- Check [FRONTEND_SETUP.md](./FRONTEND_SETUP.md)
- Review [TESTING_GUIDE.md](./TESTING_GUIDE.md)
- Check backend logs
- Open an issue on GitHub

## 🎉 Getting Started

1. **Install**: `npm install`
2. **Configure**: Copy `env.example` to `.env.local` and fill in values
3. **Start**: `npm run dev`
4. **Visit**: `http://localhost:3000`
5. **Sign In**: Click "Get Started" and authenticate with Google
6. **Chat**: Start asking questions about your analytics!

---

**Built with ❤️ using Next.js, TypeScript, and Tailwind CSS**

