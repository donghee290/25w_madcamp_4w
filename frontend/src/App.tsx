import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import BeatStudioPage from "./pages/BeatStudioPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/studio" replace />} />
        <Route path="/studio" element={<BeatStudioPage />} />
      </Routes>
    </BrowserRouter>
  );
}