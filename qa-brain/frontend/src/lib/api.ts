import type { TestCase } from "./types";
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export async function login(email: string, password: string): Promise<string> {
  const form = new FormData();
  form.append("username", email);
  form.append("password", password);
  const { data } = await api.post<{ access_token: string }>("/auth/login", form);
  localStorage.setItem("access_token", data.access_token);
  return data.access_token;
}

export async function getStoryTestCases(jiraId: string): Promise<TestCase[]> {
  const { data } = await api.get<TestCase[]>(`/api/stories/${jiraId}/test-cases`);
  return data;
}
