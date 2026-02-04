/**
 * SignupPage - 회원가입 페이지
 */

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { http } from "../api/http";
import logoImg from "../assets/logo.png";
import "../styles/SignupPage.css";

export default function SignupPage() {
    const navigate = useNavigate();
    const [id, setId] = useState("");
    const [password, setPassword] = useState("");
    const [name, setName] = useState("");
    const [job, setJob] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [passwordError, setPasswordError] = useState<string | null>(null);
    const [confirmPassword, setConfirmPassword] = useState("");
    const [confirmPasswordError, setConfirmPasswordError] = useState<string | null>(null);

    // 실시간 유효성 검사 (에러 제거용)
    useEffect(() => {
        if (password.length >= 6) {
            setPasswordError(null);
        }
    }, [password]);

    useEffect(() => {
        if (confirmPassword && password === confirmPassword) {
            setConfirmPasswordError(null);
        }
    }, [password, confirmPassword]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setPasswordError(null);
        setConfirmPasswordError(null);

        let hasError = false;

        if (password.length < 6) {
            setPasswordError("Must be at least 6 characters");
            hasError = true;
        }

        if (password !== confirmPassword) {
            setConfirmPasswordError("Passwords do not match");
            hasError = true;
        }

        if (hasError) return;

        setLoading(true);

        // 프론트엔드 디자인 확인용: API 호출 없이 바로 이동
        try {
            await http.post("/auth/register", {
                id,
                password,
                name,
                job
            });
            navigate("/login", { state: { message: "Registration complete. Please log in." } });
        } catch (err: any) {
            console.error(err);
            if (err.response && err.response.data && err.response.data.message) {
                setError(err.response.data.message);
            } else {
                setError("Registration failed. Please try again.");
            }
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

            {/* Signup Form */}
            <main className="signup-main">
                <div className="signup-card">
                    <h1 className="signup-card-title">SIGN UP</h1>

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
                                onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity('Please fill out this field.')}
                                onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                            />
                        </div>

                        <div className="form-group-password">
                            <div className="form-row">
                                <label htmlFor="password">PS:</label>
                                <input
                                    id="password"
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity('Please fill out this field.')}
                                    onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                                />
                            </div>
                            {passwordError && <div className="password-error-msg">{passwordError}</div>}
                        </div>

                        <div className="form-group-password">
                            <div className="form-row">
                                <label htmlFor="confirmPassword">RETYPE PS:</label>
                                <input
                                    id="confirmPassword"
                                    type="password"
                                    value={confirmPassword}
                                    onChange={(e) => setConfirmPassword(e.target.value)}
                                    required
                                    onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity('Please fill out this field.')}
                                    onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                                />
                            </div>
                            {confirmPasswordError && <div className="password-error-msg">{confirmPasswordError}</div>}
                        </div>

                        <div className="form-row">
                            <label htmlFor="name">NAME:</label>
                            <input
                                id="name"
                                type="text"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                required
                                onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity('Please fill out this field.')}
                                onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                            />
                        </div>

                        <div className="form-row">
                            <label htmlFor="job">JOB:</label>
                            <input
                                id="job"
                                type="text"
                                value={job}
                                onChange={(e) => setJob(e.target.value)}
                                required
                                onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity('Please fill out this field.')}
                                onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
                            />
                        </div>

                        <button type="submit" className="btn-finish" disabled={loading}>
                            {loading ? "..." : "FINISH"}
                        </button>
                    </form>
                </div>
            </main>

            {/* Subtitle */}
            <p className="signup-subtitle">Make everyday sounds into a beat!</p>
        </div>
    );
}
