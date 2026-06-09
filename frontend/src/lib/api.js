import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem("opscore_token");
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  const lang = localStorage.getItem("opscore_lang") || "ar";
  cfg.headers["X-Lang"] = lang;
  return cfg;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      const path = window.location.pathname;
      if (path !== "/login" && path !== "/register") {
        localStorage.removeItem("opscore_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);
