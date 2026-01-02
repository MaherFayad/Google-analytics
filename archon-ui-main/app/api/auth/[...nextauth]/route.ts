/**
 * NextAuth.js v5 Configuration
 * 
 * Implements Tasks 2.1, 2.2, 2.5:
 * - Task 2.1: Google OAuth Provider with GA4 analytics.readonly scope
 * - Task 2.2: JWT Callback for token capture
 * - Task 2.5: Session Callback for browser session
 * 
 * CRITICAL SCOPES:
 * - analytics.readonly: Minimum privilege for GA4 data access
 * - offline access: Required for refresh tokens
 * - prompt: consent: Forces consent screen to ensure refresh token
 */

import NextAuth, { AuthOptions, Session, User } from "next-auth";
import { JWT } from "next-auth/jwt";
import GoogleProvider from "next-auth/providers/google";

// Extend NextAuth types for OAuth tokens
declare module "next-auth" {
  interface Session {
    accessToken?: string;
    user: {
      id: string;
      email: string;
      name?: string;
      image?: string;
    };
  }

  interface User {
    id: string;
    email: string;
    name?: string;
    image?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    accessTokenExpires?: number;
    userId?: string;
    error?: string;
  }
}

/**
 * Task 2.4: Refresh access token using refresh token
 */
async function refreshAccessToken(token: JWT): Promise<JWT> {
  try {
    const url = "https://oauth2.googleapis.com/token";
    
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        client_id: process.env.GOOGLE_CLIENT_ID!,
        client_secret: process.env.GOOGLE_CLIENT_SECRET!,
        grant_type: "refresh_token",
        refresh_token: token.refreshToken!,
      }),
    });

    const refreshedTokens = await response.json();

    if (!response.ok) {
      throw refreshedTokens;
    }

    return {
      ...token,
      accessToken: refreshedTokens.access_token,
      accessTokenExpires: Date.now() + refreshedTokens.expires_in * 1000,
      refreshToken: refreshedTokens.refresh_token ?? token.refreshToken, // Fall back to old refresh token
    };
  } catch (error) {
    console.error("Error refreshing access token:", error);

    return {
      ...token,
      error: "RefreshAccessTokenError",
    };
  }
}

/**
 * Sync credentials with FastAPI backend (Task 2.3)
 */
async function syncCredentialsWithBackend(
  email: string,
  accessToken: string,
  refreshToken: string,
  expiresAt: number
): Promise<void> {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/sync`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Secret": process.env.API_SECRET || "",
      },
      body: JSON.stringify({
        email,
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_at: new Date(expiresAt).toISOString(),
      }),
    });

    if (!response.ok) {
      console.error("Failed to sync credentials with backend:", await response.text());
    }
  } catch (error) {
    console.error("Error syncing credentials:", error);
  }
}

export const authOptions: AuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      
      // Task 2.1: Critical authorization parameters
      authorization: {
        params: {
          // CRITICAL: Request GA4 analytics access
          scope: "openid email profile https://www.googleapis.com/auth/analytics.readonly",
          
          // Force consent screen to ensure refresh token is provided
          prompt: "consent",
          
          // Request offline access for refresh token
          access_type: "offline",
          
          // Use code flow for security
          response_type: "code",
        },
      },
    }),
  ],

  // Task 2.2: JWT Callback - Capture and store OAuth tokens
  callbacks: {
    async jwt({ token, account, user }: { 
      token: JWT; 
      account?: any; 
      user?: User 
    }): Promise<JWT> {
      // Initial sign in - account object is present
      if (account && user) {
        console.log("Initial sign-in, capturing OAuth tokens");
        
        // Store tokens in JWT
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.accessTokenExpires = account.expires_at * 1000; // Convert to milliseconds
        token.userId = user.id;

        // Task 2.3: Sync credentials with FastAPI backend
        if (account.refresh_token) {
          await syncCredentialsWithBackend(
            user.email,
            account.access_token,
            account.refresh_token,
            account.expires_at * 1000
          );
        }

        return token;
      }

      // Token still valid, return as is
      if (Date.now() < (token.accessTokenExpires || 0)) {
        return token;
      }

      // Task 2.4: Token expired, refresh it
      console.log("Access token expired, refreshing...");
      return refreshAccessToken(token);
    },

    // Task 2.5: Session Callback - Pass access token to browser session
    async session({ session, token }: { 
      session: Session; 
      token: JWT 
    }): Promise<Session> {
      // Add access token to session (for client-side API calls if needed)
      session.accessToken = token.accessToken;
      session.user.id = token.userId || "";

      // If token refresh failed, clear the session
      if (token.error) {
        console.error("Token error in session:", token.error);
        // Session will be invalid, user needs to re-authenticate
      }

      return session;
    },
  },

  // Use JWT strategy (not database sessions)
  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },

  // Custom pages
  pages: {
    signIn: "/auth/signin",
    error: "/auth/error",
  },

  // Debugging in development
  debug: process.env.NODE_ENV === "development",

  // JWT encryption secret
  secret: process.env.NEXTAUTH_SECRET,
};

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };



