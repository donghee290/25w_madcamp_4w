/**
 * LandingPage - SoundRoutine 첫 페이지
 * Brutalist Doodle Style
 */

import { useNavigate } from "react-router-dom";
import logoImg from "../assets/logo.png";
import signInImg from "../assets/Sign in.png";
import signUpImg from "../assets/Sign up.png";
import "../styles/LandingPage.css";

export default function LandingPage() {
    const navigate = useNavigate();

    return (
        <div className="landing-container">
            {/* Header */}
            <header className="landing-header">
                <div className="logo">
                    <img src={logoImg} alt="SoundRoutine" className="logo-icon-img" />
                    <span className="logo-text">SoundRoutine</span>
                </div>
            </header>

            {/* Main Content */}
            <main className="landing-main">
                <h1 className="landing-title-text">SoundRoutine</h1>
                <p className="landing-subtitle">Make everyday sounds into a beat!</p>

                <div className="landing-buttons">
                    <button
                        className="btn-try"
                        onClick={() => navigate("/studio", { state: { guest: true } })}
                    >
                        Try SoundRoutine
                    </button>

                    <button
                        className="btn-auth"
                        onClick={() => navigate("/login")}
                    >
                        <img src={signInImg} alt="" className="btn-drum-icon" />
                        <span>Sign in</span>
                    </button>

                    <button
                        className="btn-auth"
                        onClick={() => navigate("/signup")}
                    >
                        <img src={signUpImg} alt="" className="btn-drum-icon" />
                        <span>Sign up</span>
                    </button>
                </div>
            </main>
        </div>
    );
}
