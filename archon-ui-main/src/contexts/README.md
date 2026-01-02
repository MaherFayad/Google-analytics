# Tenant Context Implementation

## Overview

This directory implements **Task 10.1: Tenant Context Provider** for multi-tenant isolation and security.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                Application                       │
│  ┌──────────────────────────────────────────┐   │
│  │         RootProviders                     │   │
│  │  ┌────────────────────────────────────┐  │   │
│  │  │    SessionProvider (NextAuth)      │  │   │
│  │  │  ┌──────────────────────────────┐  │  │   │
│  │  │  │   TenantProvider              │  │  │   │
│  │  │  │                               │  │  │   │
│  │  │  │  - Fetches user's tenants     │  │  │   │
│  │  │  │  - Stores current tenant      │  │  │   │
│  │  │  │  - Persists to localStorage   │  │  │   │
│  │  │  └──────────────────────────────┘  │  │   │
│  │  └────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  Components use:                                │
│  - useTenant() hook                             │
│  - useApiClient() hook                          │
│  - apiClient with X-Tenant-Context header       │
└─────────────────────────────────────────────────┘
```

## Security Flow

### Frontend → Backend

```
1. User logs in via NextAuth
   ↓
2. TenantProvider fetches user's tenants from API
   GET /api/v1/tenants
   Authorization: Bearer <JWT>
   ↓
3. User selects tenant (or auto-selected)
   ↓
4. Tenant ID stored in localStorage + React Context
   ↓
5. All API calls include headers:
   Authorization: Bearer <JWT>
   X-Tenant-Context: <tenant-id>
   ↓
6. Backend validates:
   - JWT signature (JWTAuthMiddleware)
   - User belongs to tenant (TenantIsolationMiddleware)
   - Sets PostgreSQL RLS context
   ↓
7. All database queries filtered by tenant_id
```

## Files

### Core Context
- **TenantContext.tsx** - React Context and hooks for tenant management
  - `useTenant()` - Access tenant context
  - `useRequireTenant()` - Require tenant selection
  - `TenantProvider` - Context provider component

### API Integration
- **lib/api-client.ts** - Axios client with tenant interceptor
  - Automatically adds `X-Tenant-Context` header
  - Handles authentication via NextAuth
  - Type-safe API endpoint definitions

### Hooks
- **hooks/useApiClient.ts** - React hooks for API client
  - `useApiClient()` - Returns configured API client
  - `useAuthenticatedApiClient()` - Requires auth + tenant

### UI Components
- **components/tenant/TenantSelector.tsx** - Tenant selection UI
  - `TenantSelector` - Full featured selector
  - `CompactTenantSelector` - For navbar
  - `DetailedTenantSelector` - For settings page

### Providers
- **providers/RootProviders.tsx** - Application-wide provider wrapper
  - Wraps SessionProvider, QueryClientProvider, TenantProvider

## Usage Examples

### Basic Usage

```tsx
import { useTenant } from '@/contexts/TenantContext';

function MyComponent() {
  const { tenantId, currentTenant, tenants, setTenantId } = useTenant();

  return (
    <div>
      <p>Current Tenant: {currentTenant?.name}</p>
      <p>Role: {currentTenant?.role}</p>
      
      <select 
        value={tenantId || ''} 
        onChange={(e) => setTenantId(e.target.value)}
      >
        {tenants.map(t => (
          <option key={t.id} value={t.id}>{t.name}</option>
        ))}
      </select>
    </div>
  );
}
```

### Require Tenant

```tsx
import { useRequireTenant } from '@/contexts/TenantContext';

function TenantSpecificComponent() {
  // Throws error if no tenant selected
  const { tenantId, currentTenant } = useRequireTenant();

  return <div>Tenant: {currentTenant.name}</div>;
}
```

### API Calls

```tsx
import { useApiClient } from '@/hooks/useApiClient';

function DataFetcher() {
  const api = useApiClient();

  const fetchData = async () => {
    // Automatically includes:
    // - Authorization: Bearer <token>
    // - X-Tenant-Context: <tenant-id>
    const response = await api.get('/analytics/data');
    return response.data;
  };

  return <button onClick={fetchData}>Fetch Data</button>;
}
```

### Tenant Selector UI

```tsx
import { TenantSelector } from '@/components/tenant/TenantSelector';

function Header() {
  return (
    <header>
      <h1>My App</h1>
      <TenantSelector />
    </header>
  );
}
```

## Backend Integration

The frontend integrates with these backend middleware:

### 1. JWTAuthMiddleware (`python/src/server/middleware/auth.py`)
- Validates JWT signature
- Extracts user_id from token
- Sets `request.state.user_id`

### 2. TenantIsolationMiddleware (`python/src/server/middleware/tenant.py`)
- Extracts `X-Tenant-Context` header
- Validates user has access to tenant
- Sets PostgreSQL session variables for RLS
- Prevents cross-tenant data access

## Security Guarantees

✅ **JWT-based authentication** - User identity verified server-side

✅ **Server-side tenant validation** - Client cannot spoof tenant access

✅ **PostgreSQL RLS enforcement** - All queries automatically filtered

✅ **Type-safe API calls** - TypeScript prevents header mistakes

✅ **Persistent tenant selection** - Survives page refreshes

## Testing

### Manual Testing

1. **Test tenant isolation:**
   ```tsx
   // Try to manually set different tenant ID
   localStorage.setItem('archon_tenant_id', 'unauthorized-tenant-id');
   // API call should return 403 Forbidden
   ```

2. **Test tenant switching:**
   ```tsx
   const { setTenantId } = useTenant();
   setTenantId('other-tenant-id');
   // All subsequent API calls should use new tenant
   ```

3. **Test missing tenant:**
   ```tsx
   localStorage.removeItem('archon_tenant_id');
   // API calls should return 400 Bad Request
   ```

### Integration Tests

See `tests/security/test_tenant_isolation.py` for backend integration tests.

## Troubleshooting

### "X-Tenant-Context header required" error
- Ensure TenantProvider is wrapping your app
- Check that a tenant is selected
- Verify localStorage has 'archon_tenant_id'

### "Access denied" (403) error
- User may not be a member of the selected tenant
- Check tenant membership in database
- Verify JWT is valid and contains correct user_id

### "User not authenticated" (401) error
- JWT token is missing or invalid
- Ensure SessionProvider is wrapping your app
- Check NextAuth configuration

## Related Documentation

- [Task P0-2: Server-Side Tenant Derivation](../../../docs/infrastructure/P0-02-tenant-derivation.md)
- [Task P0-3: Tenant Isolation Testing](../../../docs/testing/P0-03-tenant-isolation-tests.md)
- [Multi-Tenant Security Foundation](../../../docs/architecture/multi-tenant-security.md)

