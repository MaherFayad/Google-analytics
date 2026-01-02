# Shadcn UI Setup

**Task**: 5.1: Shadcn UI Setup  
**Status**: ✅ Complete  
**Priority**: MEDIUM

## Overview

Professional UI component library setup with Shadcn UI, Radix UI primitives, and Tailwind CSS. Provides accessible, customizable, and type-safe React components.

## Components Installed

✅ **Card** - Flexible container component with header, content, and footer  
✅ **Skeleton** - Loading placeholder with animation  
✅ **Scroll Area** - Custom scrollbar with smooth scrolling  
✅ **Avatar** - User profile picture component  
✅ **Button** - Multi-variant button with size options  
✅ **Input** - Form input with consistent styling

## Installation

### 1. Install Dependencies

```bash
cd archon-ui-main
npm install
```

This will install all required packages:
- `@radix-ui/react-avatar`
- `@radix-ui/react-scroll-area`
- `@radix-ui/react-slot`
- `class-variance-authority`
- `clsx`
- `tailwind-merge`
- `tailwindcss-animate`

### 2. Configuration Files

All configuration files are already set up:

**`tailwind.config.js`** - Tailwind configuration with brand palette
**`postcss.config.js`** - PostCSS configuration
**`components.json`** - Shadcn UI configuration
**`app/globals.css`** - CSS variables and base styles
**`src/lib/utils.ts`** - Utility functions (cn helper)

## Usage

### Import Components

```tsx
// Individual imports
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';

// Or use the index for multiple imports
import { Button, Card, Avatar } from '@/components/ui';
```

### Button Component

```tsx
import { Button } from '@/components/ui/button';

// Default button
<Button>Click me</Button>

// Variants
<Button variant="default">Primary</Button>
<Button variant="secondary">Secondary</Button>
<Button variant="outline">Outline</Button>
<Button variant="ghost">Ghost</Button>
<Button variant="destructive">Delete</Button>
<Button variant="link">Link</Button>

// Sizes
<Button size="sm">Small</Button>
<Button size="default">Default</Button>
<Button size="lg">Large</Button>
<Button size="icon">🔍</Button>

// Disabled state
<Button disabled>Disabled</Button>

// As child (renders as different element)
<Button asChild>
  <a href="/dashboard">Dashboard</a>
</Button>
```

### Card Component

```tsx
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';

<Card>
  <CardHeader>
    <CardTitle>Card Title</CardTitle>
    <CardDescription>Card description goes here</CardDescription>
  </CardHeader>
  <CardContent>
    <p>Card content goes here</p>
  </CardContent>
  <CardFooter>
    <Button>Action</Button>
  </CardFooter>
</Card>
```

### Avatar Component

```tsx
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';

<Avatar>
  <AvatarImage src="https://github.com/username.png" alt="@username" />
  <AvatarFallback>UN</AvatarFallback>
</Avatar>
```

### Input Component

```tsx
import { Input } from '@/components/ui/input';

<Input type="email" placeholder="Email" />
<Input type="password" placeholder="Password" />
<Input type="text" placeholder="Search..." disabled />
```

### Skeleton Component

```tsx
import { Skeleton } from '@/components/ui/skeleton';

// Loading state
<Skeleton className="w-full h-12 rounded" />
<Skeleton className="w-[200px] h-4 mt-2" />
<Skeleton className="w-[150px] h-4 mt-2" />

// Card skeleton
<Card>
  <CardHeader>
    <Skeleton className="w-[250px] h-6" />
    <Skeleton className="w-[200px] h-4 mt-2" />
  </CardHeader>
  <CardContent>
    <Skeleton className="w-full h-32" />
  </CardContent>
</Card>
```

### Scroll Area Component

```tsx
import { ScrollArea } from '@/components/ui/scroll-area';

<ScrollArea className="h-[200px] w-full rounded-md border p-4">
  {longContent.map((item) => (
    <div key={item.id}>{item.content}</div>
  ))}
</ScrollArea>
```

## Brand Palette

The following brand colors are configured in `tailwind.config.js`:

### Primary Colors

```tsx
// Blue (Primary brand color)
brand-blue-500: #3b82f6  // Primary actions, links
brand-blue-600: #2563eb  // Hover state
brand-blue-700: #1d4ed8  // Active state

// Green (Success)
brand-green-500: #10b981  // Success messages, positive trends
brand-green-600: #16a34a  // Hover state

// Amber (Warning)
brand-amber-500: #f59e0b  // Warnings, cautions
brand-amber-600: #d97706  // Hover state

// Red (Error)
brand-red-500: #ef4444  // Errors, destructive actions
brand-red-600: #dc2626  // Hover state
```

### Using Brand Colors

```tsx
<div className="bg-brand-blue-500 text-white">
  Primary Action
</div>

<div className="text-brand-green-500">
  Success Message
</div>

<Button className="bg-brand-red-500 hover:bg-brand-red-600">
  Delete
</Button>
```

## CSS Variables

All components use CSS variables for theming. Customize in `app/globals.css`:

```css
:root {
  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --primary: 221.2 83.2% 53.3%;  /* brand-blue-500 */
  --destructive: 0 84.2% 60.2%;  /* brand-red-500 */
  --border: 214.3 31.8% 91.4%;
  --radius: 0.5rem;
}

.dark {
  --background: 222.2 84% 4.9%;
  --foreground: 210 40% 98%;
  /* ... dark mode colors */
}
```

## Dark Mode

Dark mode is configured and ready to use:

```tsx
// Add dark mode class to html element
<html className="dark">
  {/* Components automatically adapt */}
</html>

// Or use next-themes for toggle functionality
import { ThemeProvider } from "next-themes"

<ThemeProvider attribute="class" defaultTheme="system">
  {children}
</ThemeProvider>
```

## Utility Functions

### cn() - Class Name Merger

The `cn()` utility combines Tailwind classes safely:

```tsx
import { cn } from '@/lib/utils';

// Merge classes with proper precedence
<div className={cn(
  "base-class",
  isActive && "active-class",
  className
)} />

// Handles conflicts correctly
cn("px-4", "px-2") // Result: "px-2" (last wins)
```

## Customization

### Adding Custom Variants

Extend button variants in `button.tsx`:

```tsx
const buttonVariants = cva(
  "base-classes...",
  {
    variants: {
      variant: {
        // ... existing variants
        brand: "bg-brand-blue-500 text-white hover:bg-brand-blue-600",
      },
      size: {
        // ... existing sizes
        xl: "h-12 rounded-md px-10 text-lg",
      },
    },
  }
)
```

### Creating New Components

Follow the Shadcn UI pattern:

```tsx
// src/components/ui/badge.tsx

import { cn } from "@/lib/utils"
import { cva, type VariantProps } from "class-variance-authority"

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        success: "bg-brand-green-100 text-brand-green-800",
        warning: "bg-brand-amber-100 text-brand-amber-800",
        error: "bg-brand-red-100 text-brand-red-800",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
```

## Integration with Dashboard

Update existing components to use Shadcn UI:

### Before (Custom Card)

```tsx
<div className="bg-white rounded-lg shadow-sm p-6">
  <h3 className="text-xl font-semibold mb-4">Title</h3>
  <p>Content</p>
</div>
```

### After (Shadcn Card)

```tsx
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
  </CardHeader>
  <CardContent>
    <p>Content</p>
  </CardContent>
</Card>
```

### MetricCard Enhancement

```tsx
// Before
<div className="bg-white rounded-lg shadow-sm p-6">
  {/* content */}
</div>

// After - using Shadcn Card
import { Card, CardContent } from '@/components/ui/card';

<Card>
  <CardContent className="pt-6">
    {/* content */}
  </CardContent>
</Card>
```

## Accessibility

All Shadcn UI components are built with accessibility in mind:

- ✅ Keyboard navigation
- ✅ ARIA attributes
- ✅ Focus indicators
- ✅ Screen reader support
- ✅ WCAG 2.1 AA compliant

### Example: Button Accessibility

```tsx
<Button
  aria-label="Delete item"
  aria-describedby="delete-description"
  disabled={isDeleting}
>
  {isDeleting ? 'Deleting...' : 'Delete'}
</Button>
<span id="delete-description" className="sr-only">
  This action cannot be undone
</span>
```

## Testing

### Component Testing

```tsx
import { render, screen } from '@testing-library/react';
import { Button } from '@/components/ui/button';

test('renders button with text', () => {
  render(<Button>Click me</Button>);
  expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
});

test('button is disabled when prop is set', () => {
  render(<Button disabled>Click me</Button>);
  expect(screen.getByRole('button')).toBeDisabled();
});
```

## Performance

- **Tree-shaking**: Only imports used components
- **CSS Variables**: Dynamic theming without re-renders
- **Radix UI**: Optimized primitives with no runtime overhead
- **Bundle Size**: ~5-10KB per component (gzipped)

## Migration Guide

### Step 1: Update Existing Components

Replace custom UI components with Shadcn equivalents:

```tsx
// OLD: Custom button
<button className="px-4 py-2 bg-blue-500 text-white rounded">
  Click me
</button>

// NEW: Shadcn Button
<Button>Click me</Button>
```

### Step 2: Update Styling

Replace Tailwind classes with component variants:

```tsx
// OLD: Manual styling
<button className="px-6 py-3 text-lg bg-red-500 hover:bg-red-600">
  Delete
</button>

// NEW: Variants
<Button variant="destructive" size="lg">
  Delete
</Button>
```

### Step 3: Add Loading States

Use Skeleton components for loading:

```tsx
// Before
{isLoading && <div className="animate-pulse bg-gray-200 h-12" />}

// After
{isLoading && <Skeleton className="h-12" />}
```

## Troubleshooting

### Issue: CSS variables not working

**Solution**: Ensure `app/globals.css` is imported in your root layout:

```tsx
// app/layout.tsx
import './globals.css';
```

### Issue: Components not styled

**Solution**: Check Tailwind content paths in `tailwind.config.js`:

```js
content: [
  './app/**/*.{ts,tsx}',
  './src/**/*.{ts,tsx}',
],
```

### Issue: cn() not working

**Solution**: Install required dependencies:

```bash
npm install clsx tailwind-merge
```

## Resources

- [Shadcn UI Documentation](https://ui.shadcn.com/)
- [Radix UI Primitives](https://www.radix-ui.com/)
- [Tailwind CSS](https://tailwindcss.com/)
- [CVA (Class Variance Authority)](https://cva.style/)

## Next Steps

Consider adding more Shadcn UI components:

- [ ] Dialog/Modal
- [ ] Dropdown Menu
- [ ] Tabs
- [ ] Toast/Notifications
- [ ] Select
- [ ] Checkbox
- [ ] Radio Group
- [ ] Switch
- [ ] Textarea
- [ ] Label

## Contributors

- Archon AI Agent
- Implementation Date: 2026-01-02

