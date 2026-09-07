/** Preformatted block. Accepts the text either as children or via `code`. */
export default function CodeBlock({ children, code }) {
  return <pre className="stCode">{children ?? code}</pre>;
}
