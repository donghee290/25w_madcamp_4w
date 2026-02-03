import { http } from "./http";

export type LoginRequest = { email: string; password: string };
export type LoginResponse = { accessToken: string };

export async function login(payload: LoginRequest) {
  const res = await http.post<LoginResponse>("/auth/login", payload);
  return res.data;
}