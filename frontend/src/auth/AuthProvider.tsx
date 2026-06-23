import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase";
import { api } from "../lib/api";
import type { AppUser } from "../types";

interface AuthState {
  session: Session | null;
  appUser: AppUser | null;
  loading: boolean;
  /** true, пока пользователь в потоке восстановления пароля (ссылка из письма). */
  recovery: boolean;
  /** Текст ошибки из ссылки письма (ссылка устарела/недействительна), если есть. */
  authError: string;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  sendOtp: (email: string) => Promise<void>;
  verifyOtp: (email: string, token: string) => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  changePassword: (newPassword: string) => Promise<void>;
  endRecovery: () => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

/**
 * Синхронно разбираем hash из ссылки письма ДО монтирования роутера: иначе редирект
 * на /login успевает стереть hash, а одноразовое событие PASSWORD_RECOVERY теряется
 * (клиент Supabase инициализируется раньше, чем подпишется React-обработчик).
 * implicit-флоу кладёт в hash либо access_token+type=recovery, либо error_*.
 */
function parseAuthHash(): {
  recovery: boolean;
  error: string;
  accessToken: string;
  refreshToken: string;
} {
  if (typeof window === "undefined")
    return { recovery: false, error: "", accessToken: "", refreshToken: "" };
  const p = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return {
    recovery: p.get("type") === "recovery" && !!p.get("access_token"),
    error: p.get("error_description") || p.get("error_code") || p.get("error") || "",
    accessToken: p.get("access_token") || "",
    refreshToken: p.get("refresh_token") || "",
  };
}

// Захватываем токены из ссылки ОДИН РАЗ при загрузке модуля — до того как
// detectSessionInUrl или роутер очистят hash. Так смена пароля не зависит от гонки.
const initialHash = parseAuthHash();

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [appUser, setAppUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [recovery, setRecovery] = useState(initialHash.recovery);
  // Ошибка приходит только из ссылки письма на старте — сеттер не нужен.
  const [authError] = useState(initialHash.error);

  // Резолвим прикладного пользователя (роль/доступ) через API /me.
  async function loadAppUser(current: Session | null) {
    if (!current) {
      setAppUser(null);
      return;
    }
    try {
      setAppUser(await api.me());
    } catch {
      setAppUser(null);
    }
  }

  useEffect(() => {
    let active = true;
    const inRecovery =
      initialHash.recovery && !!initialHash.accessToken && !!initialHash.refreshToken;

    // В потоке восстановления ставим сессию ЯВНО из захваченных токенов (не полагаясь на
    // тайминг detectSessionInUrl) — только тогда updateUser сможет сменить пароль.
    const init = inRecovery
      ? supabase.auth.setSession({
          access_token: initialHash.accessToken,
          refresh_token: initialHash.refreshToken,
        })
      : supabase.auth.getSession();

    init.then(async ({ data }) => {
      if (!active) return;
      setSession(data.session);
      await loadAppUser(data.session);
      if (active) setLoading(false);
    });

    const { data: sub } = supabase.auth.onAuthStateChange(async (event, s) => {
      // Дубль к синхронному разбору hash: ловим событие, если успели подписаться.
      if (event === "PASSWORD_RECOVERY") setRecovery(true);
      setSession(s);
      await loadAppUser(s);
    });

    // Токены/ошибку из ссылки уже забрали в initialHash — убираем hash из адреса.
    if (window.location.hash.includes("access_token") || window.location.hash.includes("error")) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }

    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const value: AuthState = {
    session,
    appUser,
    loading,
    recovery,
    authError,
    signInWithPassword: async (email, password) => {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    },
    sendOtp: async (email) => {
      const { error } = await supabase.auth.signInWithOtp({ email });
      if (error) throw error;
    },
    verifyOtp: async (email, token) => {
      const { error } = await supabase.auth.verifyOtp({ email, token, type: "email" });
      if (error) throw error;
    },
    resetPassword: async (email) => {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: window.location.origin,
      });
      if (error) throw error;
    },
    changePassword: async (newPassword) => {
      const { error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) throw error;
    },
    endRecovery: () => setRecovery(false),
    signOut: async () => {
      await supabase.auth.signOut();
      setAppUser(null);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
