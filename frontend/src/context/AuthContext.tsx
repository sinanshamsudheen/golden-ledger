import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface User {
  id: number;
  email: string;
  folder_id: string | null;
  company_name: string | null;
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: () => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On first load, pick up ?token= or ?error= from OAuth redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    const urlError = params.get("error");
    if (urlToken) {
      localStorage.setItem("token", urlToken);
      setToken(urlToken);
    }
    if (urlError) {
      toast.error("Login failed. Please try again.");
    }
    if (urlToken || urlError) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  const refreshUser = async () => {
    if (!localStorage.getItem("token")) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const me = await api.getMe();
      setUser(me);
    } catch {
      localStorage.removeItem("token");
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshUser();
  }, [token]);

  const login = () => api.loginWithGoogle();

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
