export default function Button({ children, kind = "secondary", onClick, disabled, fullWidth, title, style }) {
  return (
    <button
      className={`stButton kind-${kind}`}
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{ width: fullWidth ? "100%" : "auto", ...style }}
    >
      {children}
    </button>
  );
}
