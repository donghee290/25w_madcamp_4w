
import { BrowserRouter, Routes, Route } from "react-router-dom";
import BeatStudioPage from "./pages/BeatStudioPage";
import LandingPage from "./pages/LandingPage";
import StudioPage from "./pages/StudioPage";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/studio" element={<BeatStudioPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/studiostudio" element={<StudioPage />} />
      </Routes>
    </BrowserRouter>
  );
}