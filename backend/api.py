"""
SoundRoutine Backend API
Google OAuth + Sound Material + Beat Studio + Project Management
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import jwt
import requests
from flask import Flask, g, jsonify, redirect, request, session, send_from_directory, send_file
from werkzeug.utils import secure_filename

from .config import AppConfig, load_config
from .db.models import User, Sound, Project, SoundAnalysis, ProjectMetadata, Sequence, NoteEvent, generate_id, utc_now
from .db.repository import get_user_repository, get_sound_repository, get_project_repository
from .auth import (
    auth_required, 
    get_current_user, 
    init_google_oauth, 
    google_oauth_bp
)


# ============================================================================
# 설정
# ============================================================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
EXTERNAL_BASE_URL = os.getenv("EXTERNAL_BASE_URL", "http://localhost:8000")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "soundroutine-secret-key-2026")

# Google OAuth 엔드포인트
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# 허용 파일 확장자
ALLOWED_EXTENSIONS = {"wav", "mp3", "m4a", "ogg", "flac"}

# 역할 목록
SOUND_ROLES = ["CORE", "ACCENT", "MOTION", "FILL", "TEXTURE"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _parse_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return default


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ============================================================================
# JWT 인증 데코레이터
# ============================================================================
# ============================================================================
# JWT 인증 데코레이터 (auth 패키지 사용)
# ============================================================================
# auth_required는 이미 import 되었습니다.



def get_current_user_id() -> Optional[str]:
    """현재 로그인한 사용자 ID 반환"""
    user = get_current_user()
    return user.get("user_id") if user else None


# ============================================================================
# App Factory
# ============================================================================
def create_app(config: Optional[AppConfig] = None) -> Flask:
    cfg = config or load_config()
    
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
    
    # 세션 쿠키 설정 (cross-origin 터널 지원)
    app.config["SESSION_COOKIE_SAMESITE"] = "None"
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    
    # 파일 업로드 설정
    app.config["UPLOAD_FOLDER"] = str(cfg.upload_root)
    app.config["OUTPUT_FOLDER"] = str(cfg.output_root)
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB
    
    _ensure_dir(cfg.data_root)
    _ensure_dir(cfg.upload_root)
    _ensure_dir(cfg.output_root)
    
    # OAuth 초기화 및 블루프린트 등록
    init_google_oauth(app)
    app.register_blueprint(google_oauth_bp)
    
    # ========================================================================
    # Health Check
    # ========================================================================
    @app.route("/health", methods=["GET"])
    def health() -> Any:
        return jsonify({
            "status": "ok",
            "service": "SoundRoutine API",
            "version": "1.0.0",
        })
    
    # ========================================================================
    # Landing Page (HTML)
    # ========================================================================
    @app.route("/")
    def index():
        """메인 랜딩 페이지"""
        user = session.get("user")
        token = session.get("access_token", "")
        
        html = f"""
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SoundRoutine - Make everyday sounds into a beat!</title>
            <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
                    background: #fafafa;
                    min-height: 100vh;
                }}
                
                /* Header */
                .header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 20px 40px;
                    background: white;
                    border-bottom: 1px solid #eee;
                }}
                .logo {{
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 24px;
                    font-weight: 700;
                    font-style: italic;
                    color: #333;
                }}
                .logo-icon {{ font-size: 28px; }}
                .nav {{
                    display: flex;
                    gap: 30px;
                }}
                .nav a {{
                    text-decoration: none;
                    color: #333;
                    font-weight: 500;
                    transition: color 0.2s;
                }}
                .nav a:hover {{ color: #FFD700; }}
                
                /* Hero Section */
                .hero {{
                    text-align: center;
                    padding: 80px 20px;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y="50" font-size="50">🎵</text></svg>') center/cover;
                    background-color: #fff;
                    position: relative;
                }}
                .hero::before {{
                    content: '';
                    position: absolute;
                    inset: 0;
                    background: rgba(255,255,255,0.9);
                }}
                .hero-content {{
                    position: relative;
                    z-index: 1;
                }}
                .hero h1 {{
                    font-size: 64px;
                    font-weight: 700;
                    font-style: italic;
                    color: #333;
                    margin-bottom: 20px;
                    text-shadow: 2px 2px 0 #FFD700;
                }}
                .hero p {{
                    font-size: 24px;
                    color: #555;
                    margin-bottom: 40px;
                }}
                
                /* Buttons */
                .btn-group {{
                    display: flex;
                    gap: 20px;
                    justify-content: center;
                    flex-wrap: wrap;
                }}
                .btn {{
                    display: inline-flex;
                    align-items: center;
                    gap: 10px;
                    padding: 16px 32px;
                    border-radius: 50px;
                    font-size: 18px;
                    font-weight: 600;
                    text-decoration: none;
                    cursor: pointer;
                    border: none;
                    transition: all 0.3s;
                }}
                .btn-primary {{
                    background: #FFD700;
                    color: #333;
                    box-shadow: 0 4px 0 #D4AF37;
                }}
                .btn-primary:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 6px 0 #D4AF37;
                }}
                .btn-google {{
                    background: white;
                    color: #333;
                    border: 2px solid #ddd;
                }}
                .btn-google:hover {{
                    background: #f8f8f8;
                    border-color: #ccc;
                }}
                .btn-logout {{
                    background: #f44336;
                    color: white;
                }}
                
                /* User Info */
                .user-info {{
                    background: #e8f5e9;
                    padding: 30px;
                    border-radius: 16px;
                    max-width: 500px;
                    margin: 30px auto;
                    text-align: left;
                }}
                .user-info h3 {{ color: #2e7d32; margin-bottom: 15px; }}
                .user-info p {{ margin: 8px 0; color: #333; }}
                .user-info img {{
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    margin-bottom: 10px;
                }}
                
                /* API Section */
                .api-section {{
                    max-width: 800px;
                    margin: 40px auto;
                    padding: 30px;
                    background: white;
                    border-radius: 16px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
                }}
                .api-section h2 {{ margin-bottom: 20px; }}
                pre {{
                    background: #2d2d2d;
                    color: #f8f8f2;
                    padding: 15px;
                    border-radius: 8px;
                    overflow-x: auto;
                    font-size: 14px;
                }}
                
                /* Token Box */
                .token-box {{
                    background: #fff8e1;
                    padding: 15px;
                    border-radius: 8px;
                    word-break: break-all;
                    font-size: 12px;
                    font-family: monospace;
                    margin: 20px 0;
                }}
                
                /* Footer */
                .footer {{
                    text-align: center;
                    padding: 20px;
                    color: #999;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <header class="header">
                <div class="logo">
                    <span class="logo-icon">♪</span>
                    <span>SoundRoutine</span>
                </div>
                <nav class="nav">
                    {"<a href='/logout'>Logout</a>" if user else "<a href='/auth/google/login'>Sign up</a>"}
                    <a href="/studio">Beat Studio</a>
                </nav>
            </header>
            
            <section class="hero">
                <div class="hero-content">
                    <h1>SoundRoutine</h1>
                    <p>Make everyday sounds into a beat!</p>
                    
                    {f'''
                    <div class="user-info">
                        <img src="{user.get('picture', '')}" alt="Profile" onerror="this.style.display='none'">
                        <h3>✅ 환영합니다!</h3>
                        <p><strong>이름:</strong> {user.get('name', '')}</p>
                        <p><strong>이메일:</strong> {user.get('email', '')}</p>
                    </div>
                    <div class="btn-group">
                        <a href="/studio" class="btn btn-primary">🎵 Beat Studio</a>
                        <a href="/logout" class="btn btn-logout">로그아웃</a>
                    </div>
                    ''' if user else '''
                    <div class="btn-group">
                        <a href="/studio" class="btn btn-primary">Try SoundRoutine</a>
                        <a href="/auth/google/login" class="btn btn-google">
                            <svg width="20" height="20" viewBox="0 0 24 24">
                                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                            </svg>
                            Sign in with Google
                        </a>
                    </div>
                    '''}
                </div>
            </section>
            
            {f'''
            <div class="api-section">
                <h2>🔑 Access Token</h2>
                <div class="token-box">{token[:100]}...</div>
                <p>이 토큰으로 API 호출 시 Authorization 헤더에 포함하세요:</p>
                <pre>Authorization: Bearer YOUR_TOKEN</pre>
            </div>
            ''' if user and token else ''}
            
            <div class="api-section">
                <h2>📡 API Endpoints</h2>
                <h4>인증</h4>
                <pre>GET  /auth/google/login     - Google 로그인
GET  /auth/google/callback  - OAuth 콜백
GET  /auth/me               - 현재 사용자 정보</pre>
                
                <h4>사운드 재료</h4>
                <pre>POST   /api/sounds              - 사운드 업로드
GET    /api/sounds              - 내 사운드 목록
GET    /api/sounds/:id          - 사운드 상세
DELETE /api/sounds/:id          - 사운드 삭제
POST   /api/sounds/:id/validate - 사운드 검증 (Use this sound?)</pre>
                
                <h4>비트 프로젝트</h4>
                <pre>POST   /api/projects            - 프로젝트 생성
GET    /api/projects            - 내 프로젝트 목록
GET    /api/projects/:id        - 프로젝트 상세
PUT    /api/projects/:id        - 프로젝트 업데이트
DELETE /api/projects/:id        - 프로젝트 삭제
POST   /api/projects/:id/generate - 비트 생성</pre>
            </div>
            
            <footer class="footer">
                <p>SoundRoutine &copy; 2026 | KAIST CS492D</p>
            </footer>
        </body>
        </html>
        """
        return html
    
    # ========================================================================
    # Beat Studio Page (HTML)
    # ========================================================================
    @app.route("/studio")
    def studio():
        """Beat Studio 페이지"""
        user = session.get("user")
        if not user:
            return redirect("/auth/google/login")
        
        html = """
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Beat Studio - SoundRoutine</title>
            <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Outfit', sans-serif;
                    background: #1a1a2e;
                    color: white;
                    min-height: 100vh;
                }
                .header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 15px 30px;
                    background: #16213e;
                    border-bottom: 1px solid #333;
                }
                .logo {
                    font-size: 20px;
                    font-weight: 700;
                    font-style: italic;
                    color: #FFD700;
                }
                .nav { display: flex; gap: 20px; }
                .nav a { color: #aaa; text-decoration: none; }
                .nav a:hover { color: white; }
                
                .container {
                    display: grid;
                    grid-template-columns: 250px 1fr 200px;
                    gap: 20px;
                    padding: 20px;
                    max-width: 1600px;
                    margin: 0 auto;
                }
                
                /* Sound Material Panel */
                .sound-panel {
                    background: #16213e;
                    border-radius: 12px;
                    padding: 20px;
                }
                .sound-panel h3 {
                    margin-bottom: 15px;
                    font-size: 16px;
                }
                .role-section {
                    margin-bottom: 20px;
                }
                .role-label {
                    display: inline-block;
                    padding: 4px 12px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                    margin-bottom: 8px;
                }
                .role-CORE { background: #FFD700; color: #333; }
                .role-ACCENT { background: #FF6B6B; color: white; }
                .role-MOTION { background: #4ECDC4; color: #333; }
                .role-FILL { background: #95E1D3; color: #333; }
                .role-TEXTURE { background: #A8E6CF; color: #333; }
                
                .sound-slot {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    padding: 10px;
                    background: #0f3460;
                    border-radius: 8px;
                    margin-bottom: 8px;
                }
                .sound-slot input {
                    flex: 1;
                    padding: 8px;
                    border: none;
                    border-radius: 4px;
                    background: #1a1a2e;
                    color: white;
                }
                .sound-slot button {
                    background: none;
                    border: none;
                    color: #aaa;
                    cursor: pointer;
                    font-size: 18px;
                }
                .sound-slot button:hover { color: #FF6B6B; }
                
                .upload-btn {
                    width: 100%;
                    padding: 12px;
                    background: #0f3460;
                    border: 2px dashed #4ECDC4;
                    border-radius: 8px;
                    color: #4ECDC4;
                    cursor: pointer;
                    margin-top: 10px;
                }
                .upload-btn:hover { background: #1a4a6e; }
                
                .generate-btn {
                    width: 100%;
                    padding: 15px;
                    background: #FFD700;
                    border: none;
                    border-radius: 8px;
                    color: #333;
                    font-size: 16px;
                    font-weight: 700;
                    cursor: pointer;
                    margin-top: 20px;
                    box-shadow: 0 4px 0 #D4AF37;
                }
                .generate-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 0 #D4AF37;
                }
                
                /* Beat Canvas */
                .canvas-panel {
                    background: #16213e;
                    border-radius: 12px;
                    padding: 20px;
                }
                .canvas-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }
                .canvas-title { font-size: 18px; font-weight: 600; }
                .page-nav {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
                .page-nav input {
                    width: 50px;
                    padding: 5px;
                    text-align: center;
                    border: none;
                    border-radius: 4px;
                    background: #0f3460;
                    color: white;
                }
                .res-btns {
                    display: flex;
                    gap: 5px;
                }
                .res-btn {
                    padding: 5px 10px;
                    border: 1px solid #333;
                    border-radius: 4px;
                    background: transparent;
                    color: #aaa;
                    cursor: pointer;
                }
                .res-btn.active {
                    background: #FFD700;
                    color: #333;
                    border-color: #FFD700;
                }
                
                .grid-container {
                    display: grid;
                    grid-template-columns: 80px repeat(16, 1fr);
                    gap: 2px;
                    background: #0f3460;
                    padding: 10px;
                    border-radius: 8px;
                    overflow-x: auto;
                }
                .grid-row { display: contents; }
                .grid-label {
                    padding: 10px;
                    font-size: 12px;
                    font-weight: 600;
                }
                .grid-cell {
                    aspect-ratio: 1;
                    background: #1a1a2e;
                    border-radius: 4px;
                    cursor: pointer;
                    transition: all 0.1s;
                }
                .grid-cell:hover { background: #2a2a4e; }
                .grid-cell.active { background: #FFD700; }
                .grid-cell.beat { background: rgba(255, 215, 0, 0.3); }
                
                /* Control Panel */
                .control-panel {
                    background: #16213e;
                    border-radius: 12px;
                    padding: 20px;
                }
                .control-panel h3 { margin-bottom: 20px; }
                .control-group {
                    margin-bottom: 20px;
                }
                .control-group label {
                    display: block;
                    margin-bottom: 5px;
                    color: #aaa;
                    font-size: 12px;
                }
                .control-group input, .control-group select {
                    width: 100%;
                    padding: 10px;
                    border: none;
                    border-radius: 4px;
                    background: #0f3460;
                    color: white;
                }
                .toggle {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }
                .toggle input[type="checkbox"] {
                    width: 40px;
                    height: 20px;
                }
                
                /* Player */
                .player {
                    grid-column: 1 / -1;
                    background: #16213e;
                    border-radius: 12px;
                    padding: 20px;
                    display: flex;
                    align-items: center;
                    gap: 20px;
                    margin-top: 20px;
                }
                .player-controls {
                    display: flex;
                    gap: 10px;
                }
                .player-btn {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    border: none;
                    background: #FFD700;
                    color: #333;
                    font-size: 18px;
                    cursor: pointer;
                }
                .progress-bar {
                    flex: 1;
                    height: 8px;
                    background: #0f3460;
                    border-radius: 4px;
                }
                .progress-fill {
                    width: 30%;
                    height: 100%;
                    background: #FFD700;
                    border-radius: 4px;
                }
                .time { color: #aaa; font-size: 14px; }
                
                .action-btns {
                    display: flex;
                    gap: 10px;
                }
                .action-btn {
                    padding: 10px 20px;
                    border: none;
                    border-radius: 8px;
                    font-weight: 600;
                    cursor: pointer;
                }
                .edit-btn { background: #4ECDC4; color: #333; }
                .save-btn { background: #FFD700; color: #333; }
            </style>
        </head>
        <body>
            <header class="header">
                <div class="logo">♪ SoundRoutine</div>
                <nav class="nav">
                    <a href="/">Home</a>
                    <a href="/logout">Logout</a>
                </nav>
            </header>
            
            <div class="container">
                <!-- Sound Material Panel -->
                <div class="sound-panel">
                    <h3>🎵 Sound Material</h3>
                    
                    <div class="role-section">
                        <span class="role-label role-CORE">CORE</span>
                        <div class="sound-slot">
                            <span>▶</span>
                            <input type="text" placeholder="No sound selected" readonly>
                            <button>×</button>
                        </div>
                    </div>
                    
                    <div class="role-section">
                        <span class="role-label role-ACCENT">ACCENT</span>
                        <div class="sound-slot">
                            <span>▶</span>
                            <input type="text" placeholder="No sound selected" readonly>
                            <button>×</button>
                        </div>
                    </div>
                    
                    <div class="role-section">
                        <span class="role-label role-MOTION">MOTION</span>
                        <div class="sound-slot">
                            <span>▶</span>
                            <input type="text" placeholder="No sound selected" readonly>
                            <button>×</button>
                        </div>
                    </div>
                    
                    <div class="role-section">
                        <span class="role-label role-FILL">FILL</span>
                        <div class="sound-slot">
                            <span>▶</span>
                            <input type="text" placeholder="No sound selected" readonly>
                            <button>×</button>
                        </div>
                    </div>
                    
                    <div class="role-section">
                        <span class="role-label role-TEXTURE">TEXTURE</span>
                        <div class="sound-slot">
                            <span>▶</span>
                            <input type="text" placeholder="No sound selected" readonly>
                            <button>×</button>
                        </div>
                    </div>
                    
                    <input type="file" id="fileInput" accept=".wav,.mp3,.m4a" style="display:none" multiple>
                    <button class="upload-btn" onclick="document.getElementById('fileInput').click()">
                        + Upload Sound
                    </button>
                    
                    <button class="generate-btn">🎹 Generate BEAT</button>
                </div>
                
                <!-- Beat Canvas -->
                <div class="canvas-panel">
                    <div class="canvas-header">
                        <span class="canvas-title">Beat Canvas</span>
                        <div class="page-nav">
                            <button>◀</button>
                            <input type="number" value="1" min="1" max="128"> / 128
                            <button>▶</button>
                        </div>
                        <div class="res-btns">
                            <button class="res-btn">8</button>
                            <button class="res-btn active">16</button>
                            <button class="res-btn">32</button>
                            <button class="res-btn">64</button>
                        </div>
                    </div>
                    
                    <div class="grid-container">
                        <!-- Header -->
                        <div class="grid-label">Bar</div>
                        <div class="grid-label">1</div>
                        <div class="grid-label">e</div>
                        <div class="grid-label">&</div>
                        <div class="grid-label">a</div>
                        <div class="grid-label">2</div>
                        <div class="grid-label">e</div>
                        <div class="grid-label">&</div>
                        <div class="grid-label">a</div>
                        <div class="grid-label">3</div>
                        <div class="grid-label">e</div>
                        <div class="grid-label">&</div>
                        <div class="grid-label">a</div>
                        <div class="grid-label">4</div>
                        <div class="grid-label">e</div>
                        <div class="grid-label">&</div>
                        <div class="grid-label">a</div>
                        
                        <!-- CORE Row -->
                        <div class="grid-label role-CORE">CORE</div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        
                        <!-- ACCENT Row -->
                        <div class="grid-label role-ACCENT">ACCENT</div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        
                        <!-- MOTION Row -->
                        <div class="grid-label role-MOTION">MOTION</div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        <div class="grid-cell"></div>
                        
                        <!-- FILL Row -->
                        <div class="grid-label role-FILL">FILL</div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell active"></div>
                        
                        <!-- TEXTURE Row -->
                        <div class="grid-label role-TEXTURE">TEXTURE</div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                        <div class="grid-cell"></div>
                    </div>
                </div>
                
                <!-- Control Panel -->
                <div class="control-panel">
                    <h3>⚙️ Control</h3>
                    
                    <div class="control-group">
                        <label>Beat Name</label>
                        <input type="text" value="My Awesome Beat">
                    </div>
                    
                    <div class="control-group">
                        <label>Group Name</label>
                        <select>
                            <option>Default Group</option>
                            <option>Lo-Fi</option>
                            <option>Hip-Hop</option>
                            <option>Electronic</option>
                        </select>
                    </div>
                    
                    <div class="control-group">
                        <label>BPM</label>
                        <input type="number" value="120" min="60" max="200">
                    </div>
                    
                    <div class="control-group">
                        <label>Time Signature</label>
                        <select>
                            <option>4/4</option>
                            <option>3/4</option>
                            <option>6/8</option>
                        </select>
                    </div>
                    
                    <div class="control-group">
                        <div class="toggle">
                            <input type="checkbox" id="progressive">
                            <label for="progressive">Progressive Mode</label>
                        </div>
                    </div>
                </div>
                
                <!-- Player -->
                <div class="player">
                    <div class="player-controls">
                        <button class="player-btn">⏮</button>
                        <button class="player-btn">▶</button>
                        <button class="player-btn">⏭</button>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill"></div>
                    </div>
                    <span class="time">0:00 / 1:32</span>
                    <div class="action-btns">
                        <a href="#" style="color: #4ECDC4;">Revert to Original</a>
                        <button class="action-btn edit-btn">Edit Beat</button>
                        <button class="action-btn save-btn">Save Beat</button>
                    </div>
                </div>
            </div>
            
            <script>
                // 그리드 셀 클릭 토글
                document.querySelectorAll('.grid-cell').forEach(cell => {
                    cell.addEventListener('click', () => {
                        cell.classList.toggle('active');
                    });
                });
                
                // 파일 업로드 처리
                document.getElementById('fileInput').addEventListener('change', async (e) => {
                    const files = e.target.files;
                    if (!files.length) return;
                    
                    const formData = new FormData();
                    for (const file of files) {
                        formData.append('files', file);
                    }
                    
                    try {
                        const token = localStorage.getItem('access_token');
                        const res = await fetch('/api/sounds', {
                            method: 'POST',
                            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
                            body: formData
                        });
                        const data = await res.json();
                        console.log('Uploaded:', data);
                        alert('사운드가 업로드되었습니다!');
                    } catch (err) {
                        console.error(err);
                        alert('업로드 실패');
                    }
                });
                
                // Generate Beat
                document.querySelector('.generate-btn').addEventListener('click', async () => {
                    alert('AI가 비트를 생성하고 있습니다...');
                    // TODO: API 호출
                });
            </script>
        </body>
        </html>
        """
        return html
    
    # ========================================================================
    # OAuth Routes
    # ========================================================================
    # Note: OAuth 라우트들은 google_oauth_bp 블루프린트로 이동되었습니다.
    # /api/auth/google/login
    # /api/auth/google/callback
    # /api/auth/me
    # /api/auth/logout

    
    # ========================================================================
    # Sound API
    # ========================================================================
    @app.route("/api/sounds", methods=["POST"])
    @auth_required
    def upload_sounds():
        """사운드 파일 업로드"""
        user_id = get_current_user_id()
        
        if "files" not in request.files and "file" not in request.files:
            return jsonify({"error": "No files provided"}), 400
        
        files = request.files.getlist("files")
        if not files:
            files = [request.files.get("file")]
        
        # 사용자 디렉토리 생성
        user_upload_dir = _ensure_dir(cfg.upload_root / user_id)
        
        sound_repo = get_sound_repository()
        existing_sounds = sound_repo.get_by_user(user_id)
        next_slot = len(existing_sounds)
        
        uploaded = []
        for i, f in enumerate(files):
            if not f or not f.filename:
                continue
            
            if not allowed_file(f.filename):
                continue
            
            if next_slot + i >= 10:
                break  # 최대 10개 슬롯
            
            filename = secure_filename(f.filename)
            unique_name = f"{generate_id()}_{filename}"
            file_path = user_upload_dir / unique_name
            f.save(str(file_path))
            
            sound = Sound(
                sound_id=generate_id(),
                user_id=user_id,
                file_path=str(file_path),
                file_name=filename,
                slot_index=next_slot + i,
                status="pending",
            )
            sound_repo.save(sound)
            uploaded.append(sound.to_dict())
        
        return jsonify({"sounds": uploaded, "count": len(uploaded)}), 201
    
    @app.route("/api/sounds", methods=["GET"])
    @auth_required
    def list_sounds():
        """내 사운드 목록"""
        user_id = get_current_user_id()
        status = request.args.get("status")
        
        sound_repo = get_sound_repository()
        sounds = sound_repo.get_by_user(user_id, status=status)
        
        return jsonify([s.to_dict() for s in sounds])
    
    @app.route("/api/sounds/<sound_id>", methods=["GET"])
    @auth_required
    def get_sound(sound_id: str):
        """사운드 상세"""
        user_id = get_current_user_id()
        
        sound_repo = get_sound_repository()
        sound = sound_repo.get(sound_id)
        
        if not sound:
            return jsonify({"error": "Sound not found"}), 404
        
        if sound.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        return jsonify(sound.to_dict())
    
    @app.route("/api/sounds/<sound_id>", methods=["DELETE"])
    @auth_required
    def delete_sound(sound_id: str):
        """사운드 삭제 (파일도 함께 삭제)"""
        user_id = get_current_user_id()
        
        sound_repo = get_sound_repository()
        sound = sound_repo.get(sound_id)
        
        if not sound:
            return jsonify({"error": "Sound not found"}), 404
        
        if sound.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        sound_repo.delete(sound_id)
        return jsonify({"message": "Sound deleted"})
    
    @app.route("/api/sounds/<sound_id>/validate", methods=["POST"])
    @auth_required
    def validate_sound(sound_id: str):
        """사운드 검증 (Use this sound? 승인)"""
        user_id = get_current_user_id()
        data = request.get_json() or {}
        
        sound_repo = get_sound_repository()
        sound = sound_repo.get(sound_id)
        
        if not sound:
            return jsonify({"error": "Sound not found"}), 404
        
        if sound.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        # AI 역할 분석 (실제로는 YAMNet/CLAP 호출)
        role = data.get("role", "CORE")
        if role not in SOUND_ROLES:
            role = "CORE"
        
        analysis = {
            "role": role,
            "dsp": {"energy": 0.5, "sharpness": 0.3, "attack": 0.1, "decay": 0.2},
            "embedding": [],
        }
        
        sound_repo.update_analysis(sound_id, analysis)
        
        return jsonify({"message": "Sound validated", "role": role})
    
    @app.route("/api/sounds/<sound_id>/file")
    @auth_required
    def serve_sound_file(sound_id: str):
        """사운드 파일 스트리밍"""
        user_id = get_current_user_id()
        
        sound_repo = get_sound_repository()
        sound = sound_repo.get(sound_id)
        
        if not sound or sound.user_id != user_id:
            return jsonify({"error": "Not found"}), 404
        
        file_path = Path(sound.file_path)
        if not file_path.exists():
            return jsonify({"error": "File not found"}), 404
        
        return send_file(str(file_path), mimetype="audio/wav")
    
    # ========================================================================
    # Project API
    # ========================================================================
    @app.route("/api/projects", methods=["POST"])
    @auth_required
    def create_project():
        """새 프로젝트 생성"""
        user_id = get_current_user_id()
        data = request.get_json() or {}
        
        metadata = ProjectMetadata(
            beat_name=data.get("beat_name", "Untitled Beat"),
            group_name=data.get("group_name", "Default Group"),
            bpm=data.get("bpm", 120),
            grid_res=data.get("grid_res", 16),
            is_progressive=data.get("is_progressive", False),
        )
        
        project = Project(
            project_id=generate_id(),
            user_id=user_id,
            metadata=metadata,
        )
        
        project_repo = get_project_repository()
        project_repo.save(project)
        
        return jsonify(project.to_dict()), 201
    
    @app.route("/api/projects", methods=["GET"])
    @auth_required
    def list_projects():
        """내 프로젝트 목록"""
        user_id = get_current_user_id()
        limit = _parse_int(request.args.get("limit"), 50)
        
        project_repo = get_project_repository()
        projects = project_repo.get_by_user(user_id, limit=limit)
        
        return jsonify([p.to_dict() for p in projects])
    
    @app.route("/api/projects/<project_id>", methods=["GET"])
    @auth_required
    def get_project(project_id: str):
        """프로젝트 상세"""
        user_id = get_current_user_id()
        
        project_repo = get_project_repository()
        project = project_repo.get(project_id)
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if project.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        return jsonify(project.to_dict())
    
    @app.route("/api/projects/<project_id>", methods=["PUT"])
    @auth_required
    def update_project(project_id: str):
        """프로젝트 업데이트"""
        user_id = get_current_user_id()
        data = request.get_json() or {}
        
        project_repo = get_project_repository()
        project = project_repo.get(project_id)
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if project.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        # 메타데이터 업데이트
        if "beat_name" in data:
            project.metadata.beat_name = data["beat_name"]
        if "group_name" in data:
            project.metadata.group_name = data["group_name"]
        if "bpm" in data:
            project.metadata.bpm = data["bpm"]
        if "grid_res" in data:
            project.metadata.grid_res = data["grid_res"]
        if "is_progressive" in data:
            project.metadata.is_progressive = data["is_progressive"]
        
        # 시퀀스 업데이트
        if "sequence" in data:
            project.sequence = Sequence.from_dict(data["sequence"])
        
        # 사운드 슬롯 업데이트
        if "sound_slots" in data:
            project.sound_slots.update(data["sound_slots"])
        
        project_repo.save(project)
        
        return jsonify(project.to_dict())
    
    @app.route("/api/projects/<project_id>", methods=["DELETE"])
    @auth_required
    def delete_project(project_id: str):
        """프로젝트 삭제"""
        user_id = get_current_user_id()
        
        project_repo = get_project_repository()
        project = project_repo.get(project_id)
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if project.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        project_repo.delete(project_id)
        return jsonify({"message": "Project deleted"})
    
    @app.route("/api/projects/<project_id>/generate", methods=["POST"])
    @auth_required
    def generate_beat(project_id: str):
        """AI 비트 생성"""
        user_id = get_current_user_id()
        
        project_repo = get_project_repository()
        project = project_repo.get(project_id)
        
        if not project:
            return jsonify({"error": "Project not found"}), 404
        
        if project.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403
        
        # TODO: 실제 AI 모델 통합
        # 지금은 샘플 패턴 생성
        events = []
        for bar in range(4):
            # CORE 패턴 (기본 비트)
            for step in [0, 4, 8, 12]:
                events.append({
                    "bar": bar,
                    "step": step,
                    "sound_id": project.sound_slots.get("CORE", ""),
                    "role": "CORE",
                    "velocity": 1.0,
                    "micro_offset": 0.0,
                })
            # ACCENT 패턴
            for step in [4, 12]:
                events.append({
                    "bar": bar,
                    "step": step,
                    "sound_id": project.sound_slots.get("ACCENT", ""),
                    "role": "ACCENT",
                    "velocity": 0.8,
                    "micro_offset": 0.02,
                })
        
        project.sequence.events = [NoteEvent.from_dict(e) for e in events]
        project.status = "completed"
        project_repo.save(project)
        
        return jsonify({
            "message": "Beat generated",
            "project": project.to_dict(),
        })
    
    # ========================================================================
    # Static Files
    # ========================================================================
    @app.route("/output/<path:filename>")
    def serve_output(filename: str) -> Any:
        return send_from_directory(cfg.output_root, filename)
    
    return app


# ============================================================================
# Entry Point
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🎵 SoundRoutine Backend API Server")
    print("=" * 60)
    print(f"EXTERNAL_BASE_URL: {EXTERNAL_BASE_URL}")
    print(f"GOOGLE_CLIENT_ID: {GOOGLE_CLIENT_ID[:30]}..." if GOOGLE_CLIENT_ID else "GOOGLE_CLIENT_ID: NOT SET")
    print("=" * 60)
    
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=True)
