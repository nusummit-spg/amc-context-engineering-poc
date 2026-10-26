import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

const ToastContext = createContext(() => {});

const VISIBLE_MS = 3800;
const EXIT_MS = 240; // matches --duration-slow so the exit animation completes before unmount

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);
  const timersRef = useRef(new Set());

  useEffect(() => {
    const timers = timersRef.current;
    return () => timers.forEach(clearTimeout);
  }, []);

  const schedule = useCallback((fn, ms) => {
    const t = setTimeout(() => {
      timersRef.current.delete(t);
      fn();
    }, ms);
    timersRef.current.add(t);
  }, []);

  const pushToast = useCallback(
    (message, icon) => {
      const id = ++idRef.current;
      setToasts((t) => [...t, { id, message, icon, leaving: false }]);
      // Flag as leaving first so the exit animation can play, then remove.
      schedule(() => {
        setToasts((t) => t.map((x) => (x.id === id ? { ...x, leaving: true } : x)));
      }, VISIBLE_MS);
      schedule(() => {
        setToasts((t) => t.filter((x) => x.id !== id));
      }, VISIBLE_MS + EXIT_MS);
    },
    [schedule]
  );

  return (
    <ToastContext.Provider value={pushToast}>
      {children}
      <div className="stToastStack" role="status" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <div className={`stToast ${t.leaving ? "stToast--leaving" : ""}`} key={t.id}>
            {t.icon ? <span aria-hidden="true">{t.icon}</span> : null}
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
