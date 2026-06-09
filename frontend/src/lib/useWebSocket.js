import { useEffect, useRef } from "react";

export function useWebSocket(onEvent) {
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  useEffect(() => {
    const token = localStorage.getItem("opscore_token");
    if (!token) return;

    const httpUrl = process.env.REACT_APP_BACKEND_URL;
    const wsUrl = httpUrl.replace(/^http/, "ws") + `/api/ws?token=${token}`;

    const connect = () => {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data);
          onEvent?.(payload);
        } catch {}
      };
      ws.onclose = () => {
        wsRef.current = null;
        reconnectRef.current = setTimeout(connect, 4000);
      };
      ws.onerror = () => {
        try { ws.close(); } catch {}
      };
    };

    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
      }
    };
  }, [onEvent]);
}
