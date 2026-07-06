import { useEffect, useMemo, useState } from "react";
import "./TaxonomyTree.css";

const LEVEL_LABEL = { 1: "Domain", 2: "Category", 3: "Subcategory", 4: "Type" };

function pathAncestors(path) {
  const parts = path.split("/");
  const out = [];
  for (let i = 1; i <= parts.length; i++) out.push(parts.slice(0, i).join("/"));
  return out;
}

function TreeNode({ node, depth, expanded, onToggle, highlightSet, activeSet, onSelect, selectedPath }) {
  const isOpen = expanded.has(node.path);
  const isActive = activeSet.has(node.path);       // exact query match — the activated branch
  const isAncestor = highlightSet.has(node.path) && !isActive; // ancestor of an activated branch
  const isSelected = selectedPath === node.path;
  const hasChildren = node.children && node.children.length > 0;

  return (
    <li className="tax-node" role="treeitem" aria-expanded={hasChildren ? isOpen : undefined}>
      <div
        className={[
          "tax-node__row",
          isActive ? "is-active" : "",
          isAncestor ? "is-ancestor" : "",
          isSelected ? "is-selected" : "",
        ].join(" ").trim()}
        style={{ paddingLeft: `${depth * 18 + 8}px` }}
      >
        <button
          className={`tax-node__twist ${hasChildren ? "" : "tax-node__twist--leaf"}`}
          onClick={() => hasChildren && onToggle(node.path)}
          aria-label={hasChildren ? (isOpen ? "Collapse" : "Expand") : undefined}
          tabIndex={hasChildren ? 0 : -1}
        >
          {hasChildren ? (isOpen ? "▾" : "▸") : "·"}
        </button>

        <button className="tax-node__label" onClick={() => onSelect(node)} title={LEVEL_LABEL[node.level]}>
          <span className="tax-node__name">{node.name}</span>
          <span className="tax-node__level eyebrow">{LEVEL_LABEL[node.level]}</span>
        </button>

        <span className={`badge ${node.document_count > 0 ? "badge--clay" : ""}`}>
          {node.document_count} doc{node.document_count === 1 ? "" : "s"}
        </span>
      </div>

      {hasChildren && isOpen && (
        <ul className="tax-node__children" role="group">
          {node.children.map((child) => (
            <TreeNode
              key={child.node_id}
              node={child}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              highlightSet={highlightSet}
              activeSet={activeSet}
              onSelect={onSelect}
              selectedPath={selectedPath}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * @param roots TaxonomyNodeOut[] (the `roots` array from GET /taxonomy)
 * @param highlightedPaths string[] — taxonomy_paths activated by a query (leaf paths).
 *        Ancestors are auto-expanded and softly highlighted; the leaf itself gets a strong highlight.
 * @param onSelectNode (node) => void — called when a node label is clicked (e.g. to load its docs)
 */
export default function TaxonomyTree({ roots, highlightedPaths = [], onSelectNode, selectedPath }) {
  const [expanded, setExpanded] = useState(() => new Set());

  const { highlightSet, activeSet } = useMemo(() => {
    const active = new Set(highlightedPaths);
    const all = new Set();
    highlightedPaths.forEach((p) => pathAncestors(p).forEach((a) => all.add(a)));
    return { highlightSet: all, activeSet: active };
  }, [highlightedPaths]);

  useEffect(() => {
    if (highlightedPaths.length === 0) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      highlightedPaths.forEach((p) => pathAncestors(p).forEach((a) => next.add(a)));
      return next;
    });
  }, [highlightedPaths]);

  function toggle(path) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) { next.delete(path); } else { next.add(path); }
      return next;
    });
  }

  function expandAll(open) {
    if (!open) { setExpanded(new Set()); return; }
    const next = new Set();
    const walk = (n) => { next.add(n.path); (n.children || []).forEach(walk); };
    roots.forEach(walk);
    setExpanded(next);
  }

  return (
    <div className="tax-tree">
      <div className="tax-tree__toolbar">
        <button className="btn btn--ghost" onClick={() => expandAll(true)}>Expand all</button>
        <button className="btn btn--ghost" onClick={() => expandAll(false)}>Collapse all</button>
        {highlightedPaths.length > 0 && (
          <span className="tax-tree__legend">
            <span className="tax-tree__swatch tax-tree__swatch--active" /> activated by query
          </span>
        )}
      </div>
      <ul className="tax-tree__roots" role="tree">
        {roots.map((root) => (
          <TreeNode
            key={root.node_id}
            node={root}
            depth={0}
            expanded={expanded}
            onToggle={toggle}
            highlightSet={highlightSet}
            activeSet={activeSet}
            onSelect={onSelectNode || (() => {})}
            selectedPath={selectedPath}
          />
        ))}
      </ul>
    </div>
  );
}
