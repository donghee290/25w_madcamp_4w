/**
 * LoginPage - 로그인 페이지
 */

import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { login } from "../api/authApi";
import logoImg from "../assets/logo.png";
import "../styles/SignupPage.css"; // Reuse SignupPage styles

export default function LoginPage() {
    const navigate = useNavigate();
    const location = useLocation();
    const [id, setId] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        try {
            await login({ id, password });

            const returnUrl = location.state?.returnUrl || "/studio";
            const savedWork = location.state?.savedWork;
            navigate(returnUrl, { state: { savedWork } });
        } catch (err) {
            setError("Login failed. Check your ID and password.");
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="signup-container">
            {/* Header */}
            <header className="signup-header">
                <div className="logo" onClick={() => navigate("/")}>
                    <img src={logoImg} alt="SoundRoutine" className="logo-icon-img" />
                    <span className="logo-text">SoundRoutine</span>
                </div>
            </header>

            {/* Title */}
            <h1 className="signup-title-text">SoundRoutine</h1>

            {/* Login Form */}
            <main className="signup-main">
                <div className="signup-card login-card">
                    <h1 className="signup-card-title">SIGN IN</h1>

                    {error && <div className="signup-error">{error}</div>}

                    <form onSubmit={handleSubmit} className="signup-form">
                        <div className="form-row">
                            <label htmlFor="id">ID:</label>
                            <input
                                id="id"
                                type="text"
                                value={id}
                                onChange={(e) => setId(e.target.value)}
                                required
                            />
                        </div>

                        <div className="form-row">
                            <label htmlFor="password">PS:</label>
                            <input
                                id="password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                            />
                        </div>

                        <button type="submit" className="btn-finish" disabled={loading}>
                            {loading ? "..." : "Log In"}
                        </button>

                        <div style={{ marginTop: "20px", textAlign: "center", fontSize: "14px", color: "#666" }}>
                            Don't have an account?{" "}
                            <span
                                onClick={() => navigate("/signup")}
                                style={{
                                    color: "#1a1a1a",
                                    fontWeight: "bold",
                                    cursor: "pointer",
                                    textDecoration: "underline"
                                }}
                            >
                                Sign up
                            </span>
                        </div>
                    </form>
                </div>
            </main>

            {/* Subtitle */}
            <p className="signup-subtitle">Make everyday sounds into a beat!</p>
        </div>
    );
}
