import { createContext, useContext, useState, useEffect, useCallback } from "react";
import * as authApi from "../api/auth.js";

const AuthContext = createContext(null);
const TOKEN_STORAGE_KEY = "gazelens_token";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // On first load, if a token is already stored, verify it's still valid
  // and fetch the user it belongs to -- keeps people logged in across refreshes.
  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    authApi
      .fetchCurrentUser(token)
      .then((u) => setUser(u))
      .catch(() => {
        // token expired/invalid -- clear it rather than leave the app in a broken state
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, [token]);

  const login = useCallback(async (email, password) => {
    setError(null);
    const result = await authApi.login({ email, password });
    localStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const signup = useCallback(async (email, password, fullName) => {
    setError(null);
    const result = await authApi.signup({ email, password, fullName });
    localStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
    setToken(result.access_token);
    setUser(result.user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, loading, error, setError, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside an AuthProvider");
  return ctx;
}
