"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { clearAuthState, loadAuthState, persistAuthState } from "@/lib/auth-storage";
import { getMe, login as loginRequest, register as registerRequest } from "@/lib/api";
import type { AuthStorageState, SessionPayload } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

type LoginPayload = {
  email: string;
  password: string;
  organization_slug?: string;
};

type RegisterPayload = {
  organization_name: string;
  organization_slug: string;
  first_name: string;
  last_name: string;
  email: string;
  password: string;
};

type AuthContextValue = {
  status: AuthStatus;
  session: SessionPayload | null;
  accessToken: string | null;
  refreshToken: string | null;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
  refreshSession: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

type AuthProviderProps = {
  children: ReactNode;
};

export function AuthProvider({ children }: AuthProviderProps) {
  const [initialState] = useState<AuthStorageState | null>(() => loadAuthState());
  const [status, setStatus] = useState<AuthStatus>(
    initialState ? "authenticated" : "anonymous",
  );
  const [session, setSession] = useState<SessionPayload | null>(initialState?.session ?? null);
  const [accessToken, setAccessToken] = useState<string | null>(initialState?.accessToken ?? null);
  const [refreshToken, setRefreshToken] = useState<string | null>(
    initialState?.refreshToken ?? null,
  );

  const applySession = useCallback(
    ({
      nextAccessToken,
      nextRefreshToken,
      nextSession,
    }: {
      nextAccessToken: string;
      nextRefreshToken: string;
      nextSession: SessionPayload;
    }) => {
      setAccessToken(nextAccessToken);
      setRefreshToken(nextRefreshToken);
      setSession(nextSession);
      setStatus("authenticated");
      persistAuthState({
        accessToken: nextAccessToken,
        refreshToken: nextRefreshToken,
        session: nextSession,
      });
    },
    [],
  );

  const logout = useCallback(() => {
    setStatus("anonymous");
    setSession(null);
    setAccessToken(null);
    setRefreshToken(null);
    clearAuthState();
  }, []);

  const refreshSession = useCallback(async () => {
    const storedState = loadAuthState();
    if (!storedState?.accessToken) {
      logout();
      return;
    }
    try {
      const nextSession = await getMe(storedState.accessToken);
      applySession({
        nextAccessToken: storedState.accessToken,
        nextRefreshToken: storedState.refreshToken,
        nextSession,
      });
    } catch {
      logout();
    }
  }, [applySession, logout]);

  const login = useCallback(
    async (payload: LoginPayload) => {
      const response = await loginRequest(payload);
      applySession({
        nextAccessToken: response.access_token,
        nextRefreshToken: response.refresh_token,
        nextSession: {
          user: response.user,
          organization: response.organization,
          membership: response.membership,
        },
      });
    },
    [applySession],
  );

  const register = useCallback(
    async (payload: RegisterPayload) => {
      const response = await registerRequest(payload);
      applySession({
        nextAccessToken: response.access_token,
        nextRefreshToken: response.refresh_token,
        nextSession: {
          user: response.user,
          organization: response.organization,
          membership: response.membership,
        },
      });
    },
    [applySession],
  );

  const value = useMemo(
    () => ({
      status,
      session,
      accessToken,
      refreshToken,
      login,
      register,
      logout,
      refreshSession,
    }),
    [status, session, accessToken, refreshToken, login, register, logout, refreshSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider.");
  }
  return value;
}
