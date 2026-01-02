# Frontend Setup Guide

This guide will help you set up and test the GA4 Analytics SaaS frontend.

## Prerequisites

- Node.js 18+ installed
- Backend API running on `http://localhost:8000`
- Google OAuth credentials configured

## Quick Start

### 1. Install Dependencies

```bash
cd archon-ui-main
npm install
```

### 2. Configure Environment

Copy the example environment file:

```bash
cp env.example .env.local
```

Edit `.env.local` and configure:

```env
# Backend API
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_API_URL=http://localhost:8000

# NextAuth
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-secret-here  # Generate with: openssl rand -base64 32

# Google OAuth (from Google Cloud Console)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

### 3. Start Development Server

```bash
npm run dev
```

The application will be available at `http://localhost:3000`

## Application Structure

### Pages

- **`/`** - Landing page with feature overview
- **`/auth/signin`** - Google OAuth sign-in page
- **`/dashboard`** - Main application dashboard (protected)
- **`/analytics`** - Analytics query interface
- **`/settings`** - User settings and GA4 connections

### Key Components

#### Chat Interface (`/dashboard`)
- **ChatLayout** - Main layout with sidebar and chat
- **ChatInterface** - Message display and input
- **HistorySidebar** - Chat session history
- **QueryInput** - Natural language query input

#### GA4 Components
- **GA4ConnectionCard** - OAuth connection status
- **MetricCard** - Display analytics metrics
- **ChartRenderer** - Visualize analytics data
- **PatternCard** - Show historical patterns

#### Hooks
- **useChatStream** - SSE streaming for chat
- **useChatSessions** - Manage chat history
- **useApiClient** - Configured API client

## Testing the Frontend

### 1. Test Landing Page

Visit `http://localhost:3000` - You should see:
- Feature grid
- "Get Started" and "Open Dashboard" buttons
- Tech stack badges

### 2. Test Authentication

1. Click "Get Started" or "Open Dashboard"
2. You'll be redirected to `/auth/signin`
3. Click "Sign in with Google"
4. Complete OAuth flow
5. You should be redirected to `/dashboard`

### 3. Test Dashboard

Once authenticated, you should see:
- **Header**: App title, tenant selector, user menu
- **GA4 Connection Banner**: Connection status or "Connect" button
- **Chat Interface**: Message input and display area
- **History Sidebar**: List of past conversations

### 4. Test Chat Functionality

1. Type a query: "Show me sessions for last 7 days"
2. Press Enter or click Send
3. Watch for:
   - User message appears
   - "Thinking..." placeholder shows
   - Streaming status updates
   - Final report with metrics and charts

### 5. Test Chat History

1. Send a few messages
2. Click "New" in the history sidebar
3. Previous conversation should be saved
4. Click on a past conversation to load it
5. Test search/filter functionality

## Environment Variables Reference

### Required

- `NEXT_PUBLIC_API_BASE_URL` - Backend API base URL
- `NEXTAUTH_URL` - Frontend URL
- `NEXTAUTH_SECRET` - Secret for session encryption
- `GOOGLE_CLIENT_ID` - Google OAuth client ID
- `GOOGLE_CLIENT_SECRET` - Google OAuth secret

### Optional

- `NEXT_PUBLIC_DEBUG` - Enable debug logging
- `NEXT_PUBLIC_SSE_RECONNECT_INTERVAL` - SSE reconnect interval (ms)
- `NEXT_PUBLIC_SSE_MAX_RETRIES` - Max SSE retry attempts
- `NEXT_PUBLIC_CACHE_TTL` - Cache time-to-live (ms)

## Common Issues

### "Connection refused" errors

**Problem**: Frontend can't reach backend API

**Solution**: 
1. Ensure backend is running on `http://localhost:8000`
2. Check `NEXT_PUBLIC_API_BASE_URL` in `.env.local`
3. Verify CORS is configured in backend

### Authentication not working

**Problem**: OAuth flow fails or redirects incorrectly

**Solution**:
1. Verify Google OAuth credentials in `.env.local`
2. Check authorized redirect URIs in Google Cloud Console:
   - `http://localhost:3000/api/auth/callback/google`
3. Ensure `NEXTAUTH_URL` matches your frontend URL

### Chat streaming not working

**Problem**: Messages don't stream or show errors

**Solution**:
1. Check browser console for SSE connection errors
2. Verify backend SSE endpoint is accessible
3. Check network tab for `/api/v1/chat/stream` requests
4. Ensure proper CORS headers for SSE

### Tenant context errors

**Problem**: API returns "Tenant context required"

**Solution**:
1. Select a tenant from the dropdown in dashboard header
2. Check browser localStorage for `archon_tenant_id`
3. Verify `X-Tenant-Context` header is sent with requests

## Development Tips

### Hot Reload

Next.js supports hot reload. Changes to components will automatically refresh.

### Type Safety

Generate types from backend OpenAPI schema:

```bash
npm run generate:types
```

### Debugging

Enable debug mode in `.env.local`:

```env
NEXT_PUBLIC_DEBUG=true
```

Check browser console for detailed logs.

### Testing Without Backend

Mock the API client in development:

```typescript
// In your component
const mockData = { /* ... */ };
if (process.env.NODE_ENV === 'development') {
  return <ChatInterface data={mockData} />;
}
```

## Production Build

### Build for Production

```bash
npm run build
```

### Start Production Server

```bash
npm start
```

### Docker Build

```bash
docker build -t ga4-frontend .
docker run -p 3000:3000 ga4-frontend
```

## Next Steps

1. **Connect GA4**: Go to Settings → Connect Google Analytics
2. **Create Chat**: Start a new conversation in Dashboard
3. **Test Queries**: Try different analytics questions
4. **Export Reports**: Use export buttons for CSV/PDF
5. **Manage History**: Browse and search past conversations

## Support

For issues or questions:
- Check backend logs: `docker-compose logs python`
- Check frontend logs: Browser console
- Review API responses: Network tab in DevTools
- Consult documentation: `/docs` folder

## Architecture

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
│                                         │
│  ┌─────────────────────────────────┐   │
│  │   Multi-Agent Orchestrator      │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐    │   │
│  │  │ Data │ │ RAG  │ │Report│    │   │
│  │  │Fetch │ │Agent │ │Agent │    │   │
│  │  └──────┘ └──────┘ └──────┘    │   │
│  └─────────────────────────────────┘   │
│         │              │                │
│  ┌──────▼──────┐ ┌────▼──────────┐    │
│  │   GA4 API   │ │  PostgreSQL   │    │
│  │             │ │  + pgvector   │    │
│  └─────────────┘ └───────────────┘    │
└─────────────────────────────────────────┘
```

## Features Implemented

✅ Google OAuth authentication  
✅ Protected routes with middleware  
✅ Real-time chat with SSE streaming  
✅ Chat history with sessions  
✅ Multi-tenant context  
✅ GA4 connection management  
✅ Metric cards and visualizations  
✅ Responsive design  
✅ Error boundaries  
✅ Loading states  
✅ Auto-reconnect for SSE  
✅ Type-safe API client  

## Features Coming Soon

🔄 CSV/PDF export  
🔄 Historical period comparison  
🔄 Advanced chart types  
🔄 Report sharing  
🔄 Admin dashboard  
🔄 Usage analytics  

