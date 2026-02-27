import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { fetchAuthConfig, fetchAuthMe, setAccessToken, setOnUnauthorized } from "./api";

interface AuthState {
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  email: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [supabase, setSupabase] = useState<SupabaseClient | null>(null);
  const [devMode, setDevMode] = useState(false);

  // Bootstrap: fetch auth config, decide if Supabase or dev-bypass
  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const cfg = await fetchAuthConfig();
        if (!cancelled) {
          if (cfg.supabase_url && cfg.supabase_anon_key) {
            const client = createClient(cfg.supabase_url, cfg.supabase_anon_key);
            setSupabase(client);
          } else {
            // No Supabase configured → local dev bypass
            setDevMode(true);
            setIsAuthenticated(true);
            setIsAdmin(true);
            setEmail("dev@local");
            setIsLoading(false);
          }
        }
      } catch {
        // Config endpoint unavailable → dev mode
        if (!cancelled) {
          setDevMode(true);
          setIsAuthenticated(true);
          setIsAdmin(true);
          setEmail("dev@local");
          setIsLoading(false);
        }
      }
    }

    init();
    return () => { cancelled = true; };
  }, []);

  // Once Supabase client is ready, listen for auth changes
  useEffect(() => {
    if (!supabase) return;

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (session?.access_token) {
        setAccessToken(session.access_token);
        setIsAuthenticated(true);
        setEmail(session.user.email ?? null);

        try {
          const me = await fetchAuthMe();
          setIsAdmin(me.is_admin);
        } catch {
          setIsAdmin(false);
        }
      } else {
        setAccessToken(null);
        setIsAuthenticated(false);
        setIsAdmin(false);
        setEmail(null);
      }
      setIsLoading(false);
    });

    // Check existing session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.access_token) {
        setAccessToken(session.access_token);
        setIsAuthenticated(true);
        setEmail(session.user.email ?? null);
        fetchAuthMe().then((me) => setIsAdmin(me.is_admin)).catch(() => setIsAdmin(false));
      }
      setIsLoading(false);
    });

    return () => subscription.unsubscribe();
  }, [supabase]);

  // Wire 401 handler
  useEffect(() => {
    setOnUnauthorized(() => {
      setIsAuthenticated(false);
      setIsAdmin(false);
      setEmail(null);
      setAccessToken(null);
      supabase?.auth.signOut();
    });
  }, [supabase]);

  const signIn = useCallback(async (email: string, password: string) => {
    if (devMode) return;
    if (!supabase) throw new Error("Auth not initialized");
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }, [supabase, devMode]);

  const signUp = useCallback(async (email: string, password: string) => {
    if (!supabase) throw new Error("Auth not initialized");
    const { error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
  }, [supabase]);

  const signOut = useCallback(async () => {
    if (devMode) return;
    setAccessToken(null);
    setIsAuthenticated(false);
    setIsAdmin(false);
    setEmail(null);
    await supabase?.auth.signOut();
  }, [supabase, devMode]);

  return (
    <AuthContext.Provider value={{ isLoading, isAuthenticated, isAdmin, email, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
