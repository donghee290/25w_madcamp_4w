import { http } from "./http";

// ========== Types ==========
export type LoginRequest = { id: string; password: string };
export type LoginResponse = { accessToken: string };

export interface User {
  id: string;
  email: string;
  name: string;
  picture?: string;
}

// ========== Storage Keys ==========
const ACCESS_TOKEN_KEY = "accessToken";
const USER_KEY = "user";

// ========== API Base URL ==========
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";

// ========== Token Management ==========
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function removeAccessToken(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

// ========== User Storage ==========
export function getStoredUser(): User | null {
  const userStr = localStorage.getItem(USER_KEY);
  if (!userStr) return null;
  try {
    return JSON.parse(userStr) as User;
  } catch {
    return null;
  }
}

export function setStoredUser(user: User): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function removeStoredUser(): void {
  localStorage.removeItem(USER_KEY);
}

// ========== Auth Status ==========
export function isAuthenticated(): boolean {
  return !!getAccessToken();
}

// ========== Google OAuth ==========
export function redirectToGoogleLogin(callbackUrl?: string): void {
  const redirectUri = callbackUrl || window.location.origin;
  const googleAuthUrl = `${API_BASE_URL}/auth/google?redirect_uri=${encodeURIComponent(redirectUri)}`;
  window.location.href = googleAuthUrl;
}

export function handleOAuthCallback(): void {
  const params = new URLSearchParams(window.location.search);
  const accessToken = params.get("access_token");
  const userDataStr = params.get("user");

  if (accessToken) {
    setAccessToken(accessToken);
  }

  if (userDataStr) {
    try {
      const user = JSON.parse(decodeURIComponent(userDataStr)) as User;
      setStoredUser(user);
    } catch (e) {
      console.error("Failed to parse user data from OAuth callback:", e);
    }
  }
}

// ========== API Calls ==========
export async function login(payload: LoginRequest): Promise<LoginResponse> {
  const res = await http.post<LoginResponse>("/auth/login", payload);
  if (res.data.accessToken) {
    setAccessToken(res.data.accessToken);
  }
  return res.data;
}

export async function getCurrentUser(): Promise<User | null> {
  const token = getAccessToken();
  if (!token) return null;

  try {
    const res = await http.get<User>("/auth/me");
    setStoredUser(res.data);
    return res.data;
  } catch (error) {
    console.error("Failed to get current user:", error);
    return null;
  }
}

export async function logout(): Promise<void> {
  try {
    await http.post("/auth/logout");
  } catch (error) {
    console.error("Logout API call failed:", error);
  } finally {
    removeAccessToken();
    removeStoredUser();
  }
}