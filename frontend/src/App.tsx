/**
 * SoundRoutine - Test Landing Page
 * Google OAuth 테스트용 랜딩 페이지
 */

import { useEffect, useState } from "react";
import "./App.css";
import {
  redirectToGoogleLogin,
  handleOAuthCallback,
  getCurrentUser,
  isAuthenticated,
  logout,
  getStoredUser,
} from "./api/authApi";
import type { User } from "./api/authApi";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    async function init() {
      // OAuth 콜백 처리 (URL에 토큰이 있는 경우)
      const params = new URLSearchParams(window.location.search);
      if (params.get("access_token")) {
        handleOAuthCallback();
        const userData = await getCurrentUser();
        if (userData) {
          setUser(userData);
          setMessage("🎉 로그인 성공!");
        }
        // URL 정리
        window.history.replaceState({}, "", "/");
      } else if (isAuthenticated()) {
        // 이미 로그인된 경우
        const storedUser = getStoredUser();
        if (storedUser) {
          setUser(storedUser);
        } else {
          const userData = await getCurrentUser();
          setUser(userData);
        }
      }
      setLoading(false);
    }
    init();
  }, []);

  const handleGoogleLogin = () => {
    // 현재 URL을 콜백으로 설정
    redirectToGoogleLogin(window.location.origin);
  };

  const handleLogout = async () => {
    await logout();
    setUser(null);
    setMessage("로그아웃되었습니다.");
  };

  if (loading) {
    return (
      <div className="app-container">
        <div className="loading-spinner"></div>
        <p>로딩 중...</p>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="logo">
          <span className="logo-icon">🎵</span>
          <span className="logo-text">SoundRoutine</span>
        </div>
        <nav className="nav">
          {user ? (
            <div className="user-info">
              {user.picture && (
                <img src={user.picture} alt="" className="user-avatar" />
              )}
              <span className="user-name">{user.name}</span>
              <button onClick={handleLogout} className="btn-logout">
                Logout
              </button>
            </div>
          ) : (
            <button onClick={handleGoogleLogin} className="btn-signup">
              Sign up
            </button>
          )}
          <a href="/studio" className="nav-link">
            Beat Studio
          </a>
        </nav>
      </header>

      {/* Hero Section */}
      <main className="hero">
        <h1 className="hero-title">SoundRoutine</h1>
        <p className="hero-subtitle">Make everyday sounds into a beat!</p>

        {message && <div className="message-toast">{message}</div>}

        <div className="hero-buttons">
          <button className="btn-primary">Try SoundRoutine</button>
          <button onClick={handleGoogleLogin} className="btn-google">
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Sign in with Google
          </button>
        </div>

        {/* 로그인 상태 표시 */}
        {user && (
          <div className="auth-status">
            <h3>✅ 인증 완료</h3>
            <div className="user-details">
              <p>
                <strong>ID:</strong> {user.id}
              </p>
              <p>
                <strong>Email:</strong> {user.email}
              </p>
              <p>
                <strong>Name:</strong> {user.name}
              </p>
            </div>
          </div>
        )}
      </main>

      {/* Debug Info */}
      <footer className="debug-info">
        <p>
          API Base URL:{" "}
          {import.meta.env.VITE_API_BASE_URL || "(not set - using relative)"}
        </p>
        <p>Auth Status: {isAuthenticated() ? "Logged In ✅" : "Not Logged In ❌"}</p>
      </footer>
    </div>
  );
}