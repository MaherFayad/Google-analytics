# 🚀 Quick Start Guide

Get the GA4 Analytics SaaS frontend running in 5 minutes!

## Prerequisites

✅ Node.js 18+ installed  
✅ Backend API running at `http://localhost:8000`  
✅ Google OAuth credentials (optional for initial testing)

## 1️⃣ Install Dependencies

```bash
cd archon-ui-main
npm install
```

## 2️⃣ Configure Environment

```bash
# Copy the template
cp env.example .env.local

# Edit .env.local
# Minimum required:
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=your-secret-here
```

**Generate secret:**
```bash
openssl rand -base64 32
```

## 3️⃣ Start Development Server

**Option A: npm**
```bash
npm run dev
```

**Option B: Quick start script**

Linux/Mac:
```bash
./start-frontend.sh
```

Windows PowerShell:
```powershell
.\start-frontend.ps1
```

## 4️⃣ Open in Browser

Visit: **http://localhost:3000**

## 🎯 What to Test First

### 1. Landing Page
- Open `http://localhost:3000`
- Should see feature grid
- Click "Open Dashboard"

### 2. Dashboard (Without Auth)
- Will redirect to `/auth/signin`
- This is expected behavior

### 3. Chat Interface (Mock Mode)
- For testing without backend/auth
- See `TESTING_GUIDE.md` for mock setup

## 🔧 Troubleshooting

### "Connection refused" error
**Problem**: Can't reach backend

**Fix**:
```bash
# Start backend
cd ..
docker-compose up -d

# Check if running
curl http://localhost:8000/health
```

### "Module not found" error
**Problem**: Missing dependencies

**Fix**:
```bash
rm -rf node_modules package-lock.json
npm install
```

### Port 3000 already in use
**Problem**: Another app using port 3000

**Fix**:
```bash
# Use different port
PORT=3001 npm run dev
```

## 📚 Next Steps

1. ✅ Frontend running → Configure Google OAuth
2. ✅ OAuth configured → Test authentication
3. ✅ Auth working → Test chat interface
4. ✅ Chat working → Test history features
5. ✅ All working → Deploy to staging

## 📖 Full Documentation

- **Setup**: [FRONTEND_SETUP.md](./FRONTEND_SETUP.md)
- **Testing**: [TESTING_GUIDE.md](./TESTING_GUIDE.md)
- **Overview**: [README.md](./README.md)

## 🆘 Need Help?

- Check browser console for errors
- Review backend logs: `docker-compose logs python`
- Verify `.env.local` configuration
- Consult documentation files

---

**Ready to start?** Run `npm run dev` and visit `http://localhost:3000` 🎉

