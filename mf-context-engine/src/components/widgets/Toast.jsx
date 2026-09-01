import { createContext, useCallback, useContext, useRef, useState } from "react";

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const pushToast = useCallback((message, icon) => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, message, icon }]);
    setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, 4000);
  }, []);

  return (
    <ToastContext.Provider value={pushToast}>
      {children}
      <div className="stToastStack">
        {toasts.map((t) => (
          <div className="stToast" key={t.id}>
            {t.icon ? `${t.icon} ` : ""}
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
