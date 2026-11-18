import axios from "axios";

export interface ApiHealth {
  status: "ok";
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 10_000,
  withCredentials: true,
  headers: {
    Accept: "application/json",
  },
});

const csrfMethods = new Set(["post", "put", "patch", "delete"]);
let csrfToken: string | null = null;
let csrfTokenPromise: Promise<string> | null = null;
let csrfTokenFetchedAt = 0;

async function getCsrfToken(): Promise<string> {
  if (csrfToken && Date.now() - csrfTokenFetchedAt < 10 * 60 * 1000) {
    return csrfToken;
  }
  if (!csrfTokenPromise) {
    csrfTokenPromise = apiClient
      .get<{ csrf_token: string }>("/csrf")
      .then(({ data }) => {
        const token = data.csrf_token;
        csrfToken = token;
        csrfTokenFetchedAt = Date.now();
        return token;
      })
      .finally(() => {
        csrfTokenPromise = null;
      });
  }
  return csrfTokenPromise;
}

apiClient.interceptors.request.use(async (config) => {
  const method = config.method?.toLowerCase();
  if (
    method &&
    csrfMethods.has(method) &&
    !config.headers.has("Authorization")
  ) {
    config.headers.set("X-CSRFToken", await getCsrfToken());
  }
  return config;
});

export async function fetchApiHealth(signal?: AbortSignal): Promise<ApiHealth> {
  const response = await apiClient.get<ApiHealth>("/health", { signal });
  return response.data;
}
