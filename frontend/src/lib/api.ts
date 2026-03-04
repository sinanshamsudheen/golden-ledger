// In dev the Vite proxy forwards /auth, /drive, /documents, /sync to the backend.
// In production set VITE_API_URL to the backend origin.
const BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }

  return res.json() as Promise<T>;
}

export const api = {
  /** Redirect browser to Google OAuth */
  loginWithGoogle(): void {
    window.location.href = `${BASE_URL}/auth/login`;
  },

  getMe(): Promise<{ id: number; email: string; folder_id: string | null }> {
    return apiFetch("/auth/me");
  },

  setFolder(folderPath: string): Promise<{ folder_id: string; folder_path: string }> {
    return apiFetch("/drive/folder", {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath }),
    });
  },

  getSyncStatus(): Promise<{
    status: string;
    next_sync: string;
    drive_connected: boolean;
    folder_configured: boolean;
    total_documents: number;
    processed_documents: number;
    pending_documents: number;
  }> {
    return apiFetch("/sync/status");
  },

  getLatestDocuments(): Promise<
    { type: string; name: string; date: string | null; description: string | null }[]
  > {
    return apiFetch("/documents/latest");
  },
};
