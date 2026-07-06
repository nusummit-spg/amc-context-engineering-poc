import "./Skeleton.css";

export function SkeletonLine({ width = "100%", height = 12 }) {
  return <div className="skel-line" style={{ width, height }} />;
}

export function SkeletonBlock({ height = 120 }) {
  return <div className="skel-block" style={{ height }} />;
}

export function SkeletonTree({ rows = 6 }) {
  return (
    <div className="skel-tree" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div className="skel-tree__row" key={i} style={{ marginLeft: (i % 3) * 18 }}>
          <span className="skel-chip" />
          <SkeletonLine width={`${52 + ((i * 13) % 30)}%`} />
        </div>
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 4 }) {
  return (
    <div className="skel-cards" aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <div className="skel-card" key={i}>
          <SkeletonLine width="70%" height={14} />
          <SkeletonLine width="45%" height={10} />
          <SkeletonLine width="90%" height={10} />
        </div>
      ))}
    </div>
  );
}
