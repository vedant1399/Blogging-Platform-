import axios from "axios";

export interface ApiHealth {
  status: "ok";
}

export interface BlogPost {
  id: string;
  title: string;
  slug: string;
  excerpt: string | null;
  content_html: string;
  cover_image_url: string | null;
  meta_description: string | null;
  seo_keywords: string[];
  canonical_url: string | null;
  read_time_minutes: number;
  published_at: string | null;
  author: {
    id: string;
    username: string;
    avatar_url: string | null;
  };
  categories: Array<{ id: string; name: string; slug: string }>;
  tags: Array<{ id: string; name: string; slug: string }>;
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

export async function fetchPostBySlug(
  slug: string,
  signal?: AbortSignal,
): Promise<BlogPost> {
  const response = await apiClient.get<{ data: BlogPost }>(
    `/posts/${encodeURIComponent(slug)}`,
    { signal },
  );
  return response.data.data;
}
