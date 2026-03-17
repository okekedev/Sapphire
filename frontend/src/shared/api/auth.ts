import client from "./client";
import type { LoginRequest, RegisterRequest, TokenResponse } from "@/shared/types/auth";

export async function login(data: LoginRequest): Promise<TokenResponse> {
  const res = await client.post<TokenResponse>("/auth/login", data);
  return res.data;
}

export async function register(data: RegisterRequest): Promise<TokenResponse> {
  const res = await client.post<TokenResponse>("/auth/register", data);
  return res.data;
}

export async function refreshToken(refresh: string): Promise<TokenResponse> {
  const res = await client.post<TokenResponse>("/auth/refresh", null, {
    params: { refresh_token: refresh },
  });
  return res.data;
}

export async function getMicrosoftLoginUrl(): Promise<string> {
  const res = await client.get<{ auth_url: string }>("/auth/microsoft/login");
  return res.data.auth_url;
}
