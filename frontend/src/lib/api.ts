import { AuthState } from '@/store/authTypes';

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/+$/, '');

export const apiUrl = (path: string) => `${API_BASE_URL}${path}`;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const hasBody = options.body !== undefined && options.body !== null;
  
  const headers: HeadersInit = {
    ...(hasBody && !isFormData && { 'Content-Type': 'application/json' }),
    ...options.headers,
  };

  const response = await fetch(apiUrl(path), {
    ...options,
    headers,
    credentials: 'include', // Important for sending/receiving cookies
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    const err = new Error(error.detail || response.statusText);
    (err as Error & { status?: number }).status = response.status;
    throw err;
  }

  return response.json();
}

export const api = {
  get: <T>(path: string, options?: RequestInit) => request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body: any, options?: RequestInit) => 
    request<T>(path, { ...options, method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body) }),
  postForm: <T>(path: string, body: Record<string, string>, options?: RequestInit) => {
    const formData = new URLSearchParams();
    for (const key in body) {
      formData.append(key, body[key]);
    }
    return request<T>(path, { 
      ...options, 
      method: 'POST', 
      headers: { ...options?.headers, 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData.toString() 
    });
  },
  patch: <T>(path: string, body: any, options?: RequestInit) =>
    request<T>(path, { ...options, method: 'PATCH', body: JSON.stringify(body) }),
  put: <T>(path: string, body: any, options?: RequestInit) => 
    request<T>(path, { ...options, method: 'PUT', body: JSON.stringify(body) }),
  delete: <T>(path: string, options?: RequestInit) => request<T>(path, { ...options, method: 'DELETE' }),
};
