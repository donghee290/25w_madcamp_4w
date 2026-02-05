import axios from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL;

export const http = axios.create({
  baseURL,
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
  },
});

// 요청 인터셉터: 토큰 자동 첨부
http.interceptors.request.use((config) => {
  const token = localStorage.getItem("accessToken"); // 저장소는 나중에 바꾸셔도 됨
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});