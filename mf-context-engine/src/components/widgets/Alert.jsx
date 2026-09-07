const ICONS = {
  info: (
    <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 15A7 7 0 108 1a7 7 0 000 14zm0-9.5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 018 5.5zm0-2.25a.9.9 0 110 1.8.9.9 0 010-1.8z"/></svg>
  ),
  success: (
    <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 15A7 7 0 108 1a7 7 0 000 14zm3.36-8.86l-3.9 4a.5.5 0 01-.72 0l-2.1-2.15a.5.5 0 11.72-.7l1.74 1.79 3.54-3.64a.5.5 0 11.72.7z"/></svg>
  ),
  warning: (
    <svg viewBox="0 0 16 16" fill="currentColor"><path d="M7.13 2.44a1 1 0 011.74 0l6.14 10.7A1 1 0 0114.14 15H1.86a1 1 0 01-.87-1.86l6.14-10.7zM8 6a.6.6 0 00-.6.6v3.2a.6.6 0 001.2 0V6.6A.6.6 0 008 6zm0 6.4a.8.8 0 100 1.6.8.8 0 000-1.6z"/></svg>
  ),
  error: (
    <svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 15A7 7 0 108 1a7 7 0 000 14zm-2.03-9.03a.5.5 0 01.7-.7L8 6.59l1.33-1.32a.5.5 0 11.7.7L8.71 7.3l1.32 1.33a.5.5 0 01-.7.7L8 8.01 6.67 9.33a.5.5 0 01-.7-.7L7.29 7.3 5.97 5.97z"/></svg>
  ),
};

export default function Alert({ type = "info", children }) {
  return (
    <div className={`stAlert stAlert--${type}`}>
      {ICONS[type]}
      <div className="stAlert-body">{children}</div>
    </div>
  );
}
