import React, {
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef,
} from "https://esm.sh/react@18";
import htm from "https://esm.sh/htm@3.1.1";

export const html = htm.bind(React.createElement);
export const Fragment = React.Fragment;
export { React, useState, useEffect, useMemo, useCallback, useRef };

let toastSequence = 0;

export function useDocumentTitle(title) {
  useEffect(() => {
    if (!title) return;
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);
}

export function Spinner({ size = 18 }) {
  const style = useMemo(
    () => ({
      width: `${size}px`,
      height: `${size}px`,
      borderWidth: `${Math.max(2, Math.round(size / 6))}px`,
    }),
    [size],
  );
  return html`<div className="spinner" role="status" style=${style}>
    <span className="visually-hidden">Cargando...</span>
  </div>`;
}

export function Skeleton({
  width = "100%",
  height = 14,
  radius = 999,
  shimmer = true,
  style,
}) {
  const merged = {
    width,
    height: typeof height === "number" ? `${height}px` : height,
    borderRadius: typeof radius === "number" ? `${radius}px` : radius,
    ...style,
  };
  const className = shimmer ? "skeleton" : "skeleton skeleton--static";
  return html`<span className=${className} style=${merged} aria-hidden="true"></span>`;
}

export function EmptyState({ icon = "📄", title, message, action }) {
  return html`<div className="empty-state-card">
    <div className="empty-state-card__icon">${icon}</div>
    <h3>${title}</h3>
    ${message ? html`<p>${message}</p>` : null}
    ${action ? html`<div className="empty-state-card__action">${action}</div>` : null}
  </div>`;
}

export function VisuallyHidden({ children }) {
  return html`<span className="visually-hidden">${children}</span>`;
}

export function useToasts({ autoDismiss = 5000 } = {}) {
  const [toasts, setToasts] = useState([]);
  const timersRef = useRef(new Map());

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const clearToasts = useCallback(() => {
    timersRef.current.forEach((timer) => clearTimeout(timer));
    timersRef.current.clear();
    setToasts([]);
  }, []);

  const pushToast = useCallback(
    ({ tone = "info", title, message, timeout = autoDismiss } = {}) => {
      toastSequence += 1;
      const id = toastSequence;
      setToasts((prev) => [
        ...prev,
        {
          id,
          tone,
          title: title || "Notificacion",
          message: message || "",
          createdAt: Date.now(),
        },
      ]);
      if (timeout) {
        const timer = setTimeout(() => dismissToast(id), timeout);
        timersRef.current.set(id, timer);
      }
      return id;
    },
    [autoDismiss, dismissToast],
  );

  useEffect(
    () => () => {
      timersRef.current.forEach((timer) => clearTimeout(timer));
      timersRef.current.clear();
    },
    [],
  );

  return { toasts, pushToast, dismissToast, clearToasts };
}

export function ToastHost({ toasts, onDismiss }) {
  if (!toasts?.length) return null;
  return html`<div className="toast-host" role="status" aria-live="polite">
    ${toasts.map((toast) => {
      const tone = toast.tone || "info";
      const className = `toast toast--${tone}`;
      return html`<div key=${toast.id} className=${className}>
        <header className="toast__header">
          <strong className="toast__title">${toast.title}</strong>
          <button
            type="button"
            className="toast__close"
            onClick=${() => onDismiss?.(toast.id)}
            aria-label="Cerrar notificacion"
          >
            &times;
          </button>
        </header>
        ${toast.message
          ? html`<div className="toast__body">${toast.message}</div>`
          : null}
      </div>`;
    })}
  </div>`;
}
