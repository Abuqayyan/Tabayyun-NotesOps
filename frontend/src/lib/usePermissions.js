// Permission-aware UI helper. Fetches the caller's effective GLOBAL permissions once
// (GET /api/rbac/my-permissions) and caches them for the session, so the sidebar and
// command palette can hide capabilities the user lacks. Pages remain the source of truth:
// they also enforce access server-side (a 403 renders a friendly empty state).
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let _cache = null;
let _promise = null;

export function fetchPermissions() {
  if (_cache) return Promise.resolve(_cache);
  if (!_promise) {
    _promise = api
      .get("/rbac/my-permissions")
      .then((r) => {
        _cache = { permissions: r.data.permissions || [], is_admin: !!r.data.is_admin };
        return _cache;
      })
      .catch(() => {
        _cache = { permissions: [], is_admin: false };
        return _cache;
      });
  }
  return _promise;
}

export function clearPermissionsCache() {
  _cache = null;
  _promise = null;
}

export function usePermissions() {
  const [perms, setPerms] = useState(_cache);
  useEffect(() => {
    let mounted = true;
    fetchPermissions().then((p) => mounted && setPerms(p));
    return () => {
      mounted = false;
    };
  }, []);
  const keys = new Set(perms?.permissions || []);
  const isAdmin = !!perms?.is_admin;
  const has = (k) => isAdmin || keys.has(k);
  const hasAny = (...ks) => ks.some(has);
  return { perms, has, hasAny, isAdmin, ready: !!perms };
}
