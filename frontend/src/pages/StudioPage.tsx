/**
 * StudioPage - 노래 생성 페이지
 * 로그인 없이도 접근 가능한 비트 메이커
 */

import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import "../styles/StudioPage.css";

import logoImg from "../assets/logo.png";

export default function StudioPage() {
    const navigate = useNavigate();
    const location = useLocation();
    const isGuest = location.state?.guest;

    // 작업 내용 상태 (이전 페이지에서 넘겨받은 데이터가 있으면 복구)
    const [workData, setWorkData] = useState(location.state?.savedWork || "");

    const handleLogout = () => {
        // TODO: Implement actual logout
        navigate("/");
    };

    const handleSignIn = () => {
        // 로그인 페이지로 갈 때 현재 작업 내용(workData)을 함께 전달
        navigate("/login", {
            state: {
                returnUrl: "/studio",
                savedWork: workData
            }
        });
    };

    return (
        <div className="studio-container">
            {/* Header */}
            <header className="studio-header">
                <div className="logo" onClick={() => navigate("/")}>
                    <img src={logoImg} alt="SoundRoutine" className="logo-icon-img" />
                    <span className="logo-text">SoundRoutine</span>
                </div>
                <nav className="studio-nav">
                    {isGuest ? (
                        <button className="btn-nav" onClick={handleSignIn}>
                            Sign in
                        </button>
                    ) : (
                        <button className="btn-nav" onClick={handleLogout}>
                            Sign out
                        </button>
                    )}
                </nav>
            </header>

            {/* Main */}
            <main className="studio-main">
                <h1 className="studio-title">Beat Studio</h1>
                <p className="studio-subtitle">Start creating your unique beat!</p>

                <div className="studio-workspace">
                    <div className="workspace-placeholder">
                        <div className="placeholder-icon">🎹</div>
                        <p>Studio workspace coming soon...</p>
                        <p className="placeholder-hint">Record everyday sounds and turn them into beats!</p>

                        {/* 임시 작업 공간: 데이터 유지 테스트용 */}
                        <div style={{ marginTop: '20px', width: '100%' }}>
                            <p style={{ fontSize: '14px', marginBottom: '8px', fontWeight: 'bold' }}>Work Memo (Data Persistence Test):</p>
                            <textarea
                                style={{
                                    width: '100%',
                                    height: '100px',
                                    padding: '10px',
                                    borderRadius: '8px',
                                    border: '2px solid #ddd',
                                    fontFamily: 'inherit'
                                }}
                                placeholder="Write something here as a guest, then sign in..."
                                value={workData}
                                onChange={(e) => setWorkData(e.target.value)}
                            />
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
}
