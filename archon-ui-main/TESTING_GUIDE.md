# Frontend Testing Guide

Complete guide to test all frontend features of the GA4 Analytics SaaS application.

## Prerequisites

Before testing, ensure:

1. ✅ Backend API is running (`http://localhost:8000`)
2. ✅ PostgreSQL database is running
3. ✅ Redis is running (for caching)
4. ✅ `.env.local` is configured with valid credentials
5. ✅ Frontend dev server is running (`npm run dev`)

## Test Checklist

### 1. Landing Page (`/`)

**URL**: `http://localhost:3000`

**Expected**:
- [ ] Page loads without errors
- [ ] Feature grid displays 4 features
- [ ] "Get Started" button links to `/auth/signin`
- [ ] "Open Dashboard" button links to `/dashboard`
- [ ] Tech stack badges visible
- [ ] Responsive on mobile

**How to Test**:
```bash
# Open in browser
open http://localhost:3000

# Check console for errors (should be none)
# Resize window to test responsiveness
```

---

### 2. Authentication Flow

#### 2.1 Sign In Page (`/auth/signin`)

**URL**: `http://localhost:3000/auth/signin`

**Expected**:
- [ ] Google sign-in button visible
- [ ] Loading state shows when clicked
- [ ] Redirects to Google OAuth
- [ ] After auth, redirects to `/dashboard`

**How to Test**:
```bash
1. Navigate to /auth/signin
2. Click "Sign in with Google"
3. Complete Google OAuth flow
4. Verify redirect to /dashboard
5. Check session in browser DevTools → Application → Cookies
```

#### 2.2 Protected Routes

**Expected**:
- [ ] Accessing `/dashboard` without auth → redirects to `/auth/signin`
- [ ] After sign-in → can access `/dashboard`
- [ ] Session persists on page refresh

**How to Test**:
```bash
# Test 1: Unauthenticated access
1. Clear cookies (DevTools → Application → Clear site data)
2. Navigate to http://localhost:3000/dashboard
3. Should redirect to /auth/signin

# Test 2: Authenticated access
1. Sign in via /auth/signin
2. Navigate to /dashboard
3. Should load dashboard
4. Refresh page
5. Should stay on dashboard (session persists)
```

---

### 3. Dashboard (`/dashboard`)

**URL**: `http://localhost:3000/dashboard`

**Expected**:
- [ ] Header shows app title, tenant selector, user info
- [ ] GA4 connection banner displays
- [ ] Chat interface loads
- [ ] History sidebar shows (left side)
- [ ] Footer displays
- [ ] No console errors

**Components to Verify**:

#### 3.1 Header
- [ ] App title: "GA4 Analytics Chat"
- [ ] Tenant selector dropdown
- [ ] Connection status indicator
- [ ] User name and email
- [ ] Settings icon button
- [ ] Sign out button

#### 3.2 GA4 Connection Banner
- [ ] Shows "No Connections Yet" if not connected
- [ ] "Connect Google Analytics" button works
- [ ] After connection: shows property list
- [ ] Property details: ID, last sync, token expiry
- [ ] "Reconnect" button for expired tokens

#### 3.3 Chat Interface
- [ ] Welcome message displays
- [ ] Example queries shown
- [ ] Input field accepts text
- [ ] Send button enabled when text entered
- [ ] Enter key sends message

#### 3.4 History Sidebar
- [ ] "Chat History" title
- [ ] "New" button creates new session
- [ ] Search input filters sessions
- [ ] Empty state shows when no history
- [ ] Session count displays in footer

---

### 4. Chat Functionality

#### 4.1 Send a Message

**Test Query**: "Show me sessions for the last 7 days"

**Expected Flow**:
1. [ ] User message appears immediately (blue bubble, right-aligned)
2. [ ] Assistant placeholder appears (white bubble, left-aligned)
3. [ ] "Thinking..." status shows
4. [ ] Status updates: "Fetching data...", "Analyzing...", etc.
5. [ ] Final report appears with:
   - [ ] Answer text
   - [ ] Metric cards (if applicable)
   - [ ] Charts (if applicable)
   - [ ] Confidence badge
6. [ ] Timestamp shows below each message
7. [ ] Auto-scrolls to bottom

**How to Test**:
```bash
1. Open dashboard
2. Type query in input field
3. Press Enter or click Send
4. Watch for streaming updates
5. Verify final report renders correctly
6. Check browser Network tab for SSE connection
```

#### 4.2 SSE Streaming

**Expected**:
- [ ] EventSource connection opens to `/api/v1/chat/stream`
- [ ] Status events update UI
- [ ] Result event renders final report
- [ ] Connection closes after result
- [ ] Errors handled gracefully

**How to Test**:
```bash
# In browser DevTools → Network tab
1. Filter by "EventStream" or "SSE"
2. Send a chat message
3. Click on the SSE request
4. View "EventStream" tab
5. Should see events: status, status, ..., result
```

#### 4.3 Multiple Messages

**Test Queries**:
1. "Show me sessions for last 7 days"
2. "What's my bounce rate?"
3. "Compare desktop vs mobile traffic"

**Expected**:
- [ ] Each message appears in order
- [ ] Previous messages stay visible
- [ ] Scroll area handles multiple messages
- [ ] Can scroll through history

#### 4.4 Error Handling

**Test**: Disconnect backend API

**Expected**:
- [ ] Error message displays
- [ ] "Retry" button appears
- [ ] Can retry failed message
- [ ] Connection status shows error

**How to Test**:
```bash
1. Stop backend: docker-compose down python
2. Send a message in chat
3. Should show error after timeout
4. Click "Retry" button
5. Start backend: docker-compose up -d python
6. Retry should succeed
```

---

### 5. Chat History

#### 5.1 Create New Session

**Expected**:
- [ ] Click "New" button
- [ ] Chat clears
- [ ] New session created in sidebar
- [ ] Session title auto-generated

**How to Test**:
```bash
1. Send a few messages
2. Click "New" in history sidebar
3. Chat should clear
4. New session appears in sidebar
5. Previous session still visible in list
```

#### 5.2 Load Previous Session

**Expected**:
- [ ] Click on session in sidebar
- [ ] Chat loads with previous messages
- [ ] Messages display correctly
- [ ] Can continue conversation

**How to Test**:
```bash
1. Create 2-3 sessions with different queries
2. Click on an older session
3. Messages should load
4. Send a new message
5. Should append to that session
```

#### 5.3 Search Sessions

**Expected**:
- [ ] Type in search box
- [ ] Sessions filter in real-time
- [ ] Shows "No matching conversations" if none found
- [ ] Clear search shows all sessions

**How to Test**:
```bash
1. Create sessions with queries: "sessions", "bounce rate", "traffic"
2. Search for "bounce"
3. Should show only "bounce rate" session
4. Clear search
5. All sessions visible again
```

#### 5.4 Rename Session

**Expected**:
- [ ] Click edit icon on session
- [ ] Input field appears
- [ ] Can type new title
- [ ] Enter saves, Escape cancels
- [ ] Title updates in list

**How to Test**:
```bash
1. Hover over a session
2. Click edit icon (pencil)
3. Type new title: "My Analytics Report"
4. Press Enter
5. Title should update
```

#### 5.5 Delete Session

**Expected**:
- [ ] Click delete icon (trash)
- [ ] Confirmation dialog appears
- [ ] Confirm deletes session
- [ ] Session removed from list
- [ ] If current session, chat clears

**How to Test**:
```bash
1. Hover over a session
2. Click delete icon (trash)
3. Confirm deletion
4. Session should disappear
5. If it was loaded, chat should clear
```

---

### 6. Report Rendering

#### 6.1 Metric Cards

**Expected**:
- [ ] Cards display in grid (2-4 columns)
- [ ] Each card shows: label, value, change, trend
- [ ] Trend arrows (up/down/neutral)
- [ ] Colors: green (up), red (down), gray (neutral)

**Test Query**: "Show me key metrics for last week"

#### 6.2 Charts

**Expected**:
- [ ] Charts render without errors
- [ ] Supported types: line, bar, pie, area
- [ ] Responsive to container width
- [ ] Hover shows tooltips
- [ ] Legend displays

**Test Query**: "Show me sessions trend over last 30 days"

#### 6.3 Confidence Badge

**Expected**:
- [ ] Badge shows confidence percentage
- [ ] Colors: green (high), yellow (medium), red (low)
- [ ] Tooltip explains confidence level

---

### 7. Tenant Management

#### 7.1 Tenant Selector

**Expected**:
- [ ] Dropdown shows available tenants
- [ ] Can select different tenant
- [ ] Selection persists in localStorage
- [ ] API requests include `X-Tenant-Context` header

**How to Test**:
```bash
# In browser DevTools → Application → Local Storage
1. Check for 'archon_tenant_id' key
2. Select different tenant from dropdown
3. Value should update
4. Send a chat message
5. Network tab → Check request headers
6. Should include: X-Tenant-Context: <tenant_id>
```

---

### 8. Responsive Design

#### 8.1 Desktop (1920x1080)

**Expected**:
- [ ] Sidebar visible by default
- [ ] Chat takes remaining width
- [ ] Metric cards in 4 columns
- [ ] All features accessible

#### 8.2 Tablet (768x1024)

**Expected**:
- [ ] Sidebar toggleable
- [ ] Chat full width when sidebar hidden
- [ ] Metric cards in 2 columns
- [ ] Touch-friendly buttons

#### 8.3 Mobile (375x667)

**Expected**:
- [ ] Sidebar overlay (not side-by-side)
- [ ] Hamburger menu to toggle sidebar
- [ ] Metric cards in 1 column
- [ ] Scrollable chat
- [ ] Input field sticky at bottom

**How to Test**:
```bash
# In browser DevTools
1. Toggle device toolbar (Cmd+Shift+M / Ctrl+Shift+M)
2. Select different devices
3. Test all features at each size
```

---

### 9. Performance

#### 9.1 Initial Load

**Expected**:
- [ ] Page loads in < 2 seconds
- [ ] No layout shift
- [ ] Smooth transitions

**How to Test**:
```bash
# In browser DevTools → Lighthouse
1. Run Lighthouse audit
2. Check Performance score (should be > 80)
3. Check First Contentful Paint (should be < 1.5s)
```

#### 9.2 Chat Streaming

**Expected**:
- [ ] First token in < 500ms
- [ ] Smooth streaming updates
- [ ] No UI freezing
- [ ] Responsive during streaming

#### 9.3 Large Sessions

**Test**: Load session with 50+ messages

**Expected**:
- [ ] Loads without lag
- [ ] Scrolling is smooth
- [ ] Can send new messages
- [ ] Search still works

---

### 10. Error Scenarios

#### 10.1 Network Errors

**Test**: Disconnect internet

**Expected**:
- [ ] Error message displays
- [ ] Retry button available
- [ ] Graceful degradation
- [ ] No app crash

#### 10.2 API Errors

**Test**: Backend returns 500 error

**Expected**:
- [ ] Error message shows
- [ ] Can retry request
- [ ] Previous messages still visible
- [ ] App remains functional

#### 10.3 Invalid Queries

**Test**: Send gibberish query

**Expected**:
- [ ] Backend handles gracefully
- [ ] Returns "I don't understand" message
- [ ] Can send new query
- [ ] No app crash

---

### 11. Browser Compatibility

Test in multiple browsers:

- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)

**Features to verify in each**:
- [ ] Authentication works
- [ ] SSE streaming works
- [ ] Charts render correctly
- [ ] Responsive design works

---

### 12. Accessibility

#### 12.1 Keyboard Navigation

**Expected**:
- [ ] Tab through all interactive elements
- [ ] Enter sends message
- [ ] Escape closes modals
- [ ] Focus visible on all elements

#### 12.2 Screen Reader

**Expected**:
- [ ] Semantic HTML (headings, landmarks)
- [ ] ARIA labels on buttons
- [ ] Alt text on images
- [ ] Status updates announced

#### 12.3 Color Contrast

**Expected**:
- [ ] Text readable on backgrounds
- [ ] Meets WCAG AA standards
- [ ] Works in high contrast mode

---

## Automated Testing

### Run Type Checks

```bash
npm run type-check
```

**Expected**: No TypeScript errors

### Run Linter

```bash
npm run lint
```

**Expected**: No ESLint errors

### Build for Production

```bash
npm run build
```

**Expected**: Build succeeds without errors

---

## Common Issues & Solutions

### Issue: "Connection refused" on API calls

**Solution**:
1. Check backend is running: `docker-compose ps`
2. Verify `NEXT_PUBLIC_API_BASE_URL` in `.env.local`
3. Check CORS configuration in backend

### Issue: SSE not working

**Solution**:
1. Check browser supports EventSource
2. Verify SSE endpoint in backend
3. Check for proxy/firewall blocking SSE
4. Try in different browser

### Issue: Authentication loop

**Solution**:
1. Clear all cookies
2. Check `NEXTAUTH_URL` matches frontend URL
3. Verify Google OAuth redirect URIs
4. Check `NEXTAUTH_SECRET` is set

### Issue: Charts not rendering

**Solution**:
1. Check console for Recharts errors
2. Verify chart data format
3. Check chart config schema
4. Try different chart type

---

## Test Report Template

Use this template to document test results:

```markdown
# Test Report - [Date]

## Environment
- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Browser: Chrome 120
- OS: macOS 14

## Test Results

### Authentication
- [ ] Sign in: PASS
- [ ] Sign out: PASS
- [ ] Protected routes: PASS

### Chat Functionality
- [ ] Send message: PASS
- [ ] SSE streaming: PASS
- [ ] Error handling: PASS

### Chat History
- [ ] Create session: PASS
- [ ] Load session: PASS
- [ ] Search: PASS
- [ ] Delete: PASS

### Responsive Design
- [ ] Desktop: PASS
- [ ] Tablet: PASS
- [ ] Mobile: PASS

## Issues Found
1. [Issue description]
   - Severity: High/Medium/Low
   - Steps to reproduce
   - Expected vs Actual

## Notes
[Any additional observations]
```

---

## Next Steps After Testing

1. ✅ All tests pass → Ready for staging deployment
2. ❌ Tests fail → Fix issues and retest
3. 📝 Document any bugs found
4. 🚀 Deploy to staging environment
5. 🔄 Repeat tests in staging
6. ✨ Deploy to production

---

## Support

If you encounter issues during testing:

1. Check browser console for errors
2. Check backend logs: `docker-compose logs python`
3. Review Network tab in DevTools
4. Consult `FRONTEND_SETUP.md` for configuration help
5. Check GitHub issues for known problems

