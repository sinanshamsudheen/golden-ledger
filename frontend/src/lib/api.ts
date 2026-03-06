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

export interface DealDocSlot {
  id: number;
  file_id: string;
  name: string;
  date: string | null;
  description: string | null;
  vectorizer_doc_id: string | null;
}

export interface DealDocSlots {
  pitch_deck: DealDocSlot | null;
  investment_memo: DealDocSlot | null;
  prescreening_report: DealDocSlot | null;
  meeting_minutes: DealDocSlot | null;
}

export interface ArchivedDoc {
  id: number;
  file_id: string;
  type: string;
  name: string;
  date: string | null;
}

export interface LockedFileDoc {
  id: number;
  file_id: string;
  name: string;
  date: string | null;
}

export interface LockedFileWithDeal {
  id: number;
  file_id: string;
  name: string;
  date: string | null;
  deal_id: number | null;
  deal_name: string | null;
}

export interface DealResponse {
  id: number;
  name: string;
  documents: DealDocSlots;
  archived: ArchivedDoc[];
  doc_count: number;
  investment_type: string | null;
  deal_status: string | null;
  deal_reason: string | null;
  locked_files: LockedFileDoc[];
}

export const api = {
  /** Redirect browser to Google OAuth */
  loginWithGoogle(): void {
    window.location.href = `${BASE_URL}/auth/login`;
  },

  getMe(): Promise<{ id: number; email: string; folder_id: string | null; company_name: string | null }> {
    return apiFetch("/auth/me");
  },

  updateProfile(data: { company_name: string }): Promise<{ id: number; email: string; folder_id: string | null; company_name: string | null }> {
    return apiFetch("/auth/me", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
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

  getAllDocuments(): Promise<
    { id: number; file_id: string; type: string; name: string; date: string | null; description: string | null; status: string; deal_id: number | null; deal_name: string | null; version_status: string }[]
  > {
    return apiFetch("/documents/all");
  },

  getDeals(): Promise<DealResponse[]> {
    return apiFetch("/documents/deals");
  },

  getDeal(dealId: number): Promise<DealResponse> {
    return apiFetch(`/documents/deals/${dealId}`);
  },

  getLockedFiles(): Promise<LockedFileWithDeal[]> {
    return apiFetch("/documents/locked");
  },

  getDocumentStats(): Promise<{
    total_validated: number;
    shortlisted: number;
    archived: number;
    knowledge_base: number;
    duplicates: number;
  }> {
    return apiFetch("/documents/stats");
  },
};
