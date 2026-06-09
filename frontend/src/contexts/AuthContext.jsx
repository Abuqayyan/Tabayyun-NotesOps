import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("opscore_token");
    if (!token) { setLoading(false); return; }
    api.get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => localStorage.removeItem("opscore_token"))
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    if (r.data.otp_required) {
      return { otpRequired: true, otpId: r.data.otp_id, emailSent: r.data.email_sent, sessionHours: r.data.session_hours };
    }
    localStorage.setItem("opscore_token", r.data.token);
    setUser(r.data.user);
    return { otpRequired: false, user: r.data.user };
  };

  const verifyOtp = async (otpId, code) => {
    const r = await api.post("/auth/otp/verify", { otp_id: otpId, code });
    localStorage.setItem("opscore_token", r.data.token);
    setUser(r.data.user);
    return r.data.user;
  };

  const resendOtp = async (otpId) => {
    const r = await api.post("/auth/otp/resend", { otp_id: otpId });
    return r.data;
  };

  const acceptInvite = async (token, tempPassword) => {
    const r = await api.post("/auth/accept-invite", { token, temp_password: tempPassword });
    localStorage.setItem("opscore_token", r.data.token);
    setUser(r.data.user);
    return { user: r.data.user, mustChangePassword: r.data.must_change_password };
  };

  const register = async (email, password, name) => {
    const r = await api.post("/auth/register", { email, password, name });
    localStorage.setItem("opscore_token", r.data.token);
    setUser(r.data.user);
    return r.data.user;
  };

  const logout = () => {
    localStorage.removeItem("opscore_token");
    setUser(null);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, verifyOtp, resendOtp, acceptInvite, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
