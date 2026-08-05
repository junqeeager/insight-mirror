import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  consumeUnauthorizedFlag,
  resetUnauthorizedFlag,
  setAuthToken,
  setUnauthorizedHandler,
} from "../api/client";
import type { User } from "../types";
import { AUTH_STORAGE_KEY as STORAGE_KEY } from "./storage";

interface StoredAuth {
  token: string;
  user: User;
}

interface AuthContextValue {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  loginOpen: boolean;
  openLogin: () => void;
  closeLogin: () => void;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<string>;
  logout: () => Promise<void>;
  requireAuth: (action?: () => void | Promise<void>) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredAuth(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredAuth;
    if (!parsed.token || !parsed.user?.username) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [stored, setStored] = useState<StoredAuth | null>(() => readStoredAuth());
  const [loginOpen, setLoginOpen] = useState(false);
  const pendingAction = useRef<(() => void | Promise<void>) | null>(null);

  const persist = useCallback((next: StoredAuth | null) => {
    setStored(next);
    if (next) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      setAuthToken(next.token);
    } else {
      localStorage.removeItem(STORAGE_KEY);
      setAuthToken(null);
    }
  }, []);

  useEffect(() => {
    setAuthToken(stored?.token ?? null);
  }, [stored]);

  const openLogin = useCallback(() => setLoginOpen(true), []);
  const closeLogin = useCallback(() => {
    pendingAction.current = null;
    setLoginOpen(false);
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      const data = await apiLogin(username, password);
      persist({ token: data.token, user: data.user });
      setLoginOpen(false);
      const next = pendingAction.current;
      pendingAction.current = null;
      if (next) {
        window.setTimeout(() => {
          void next();
        }, 0);
      }
    },
    [persist],
  );

  const register = useCallback(
    async (username: string, password: string) => {
      const data = await apiRegister(username, password);
      return data.status === "pending"
        ? "注册成功，请等待管理员审核后登录"
        : "注册成功";
    },
    [],
  );

  const logout = useCallback(async () => {
    const token = stored?.token;
    pendingAction.current = null;
    persist(null);
    setLoginOpen(false);
    if (token) {
      try {
        await apiLogout(token);
      } catch {
        // 本地登出优先，服务端失效失败不阻塞
      }
    }
  }, [persist, stored]);

  const requireAuth = useCallback(
    (action?: () => void | Promise<void>) => {
      if (stored?.token && stored.user) {
        resetUnauthorizedFlag();
        pendingAction.current = action ?? null;
        if (action) {
          Promise.resolve(action()).then(
            () => {
              if (!consumeUnauthorizedFlag() && pendingAction.current === action) {
                pendingAction.current = null;
              }
            },
            () => {
              if (!consumeUnauthorizedFlag() && pendingAction.current === action) {
                pendingAction.current = null;
              }
            },
          );
        }
        return true;
      }
      pendingAction.current = action ?? null;
      setLoginOpen(true);
      return false;
    },
    [stored],
  );

  useEffect(() => {
    setUnauthorizedHandler(() => {
      persist(null);
      setLoginOpen(true);
    });
    return () => setUnauthorizedHandler(null);
  }, [persist]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: stored?.user ?? null,
      token: stored?.token ?? null,
      isAuthenticated: Boolean(stored?.token && stored.user),
      isAdmin: stored?.user?.role === "admin",
      loginOpen,
      openLogin,
      closeLogin,
      login,
      register,
      logout,
      requireAuth,
    }),
    [
      stored,
      loginOpen,
      openLogin,
      closeLogin,
      login,
      register,
      logout,
      requireAuth,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}
