export default function QuerySelector({ queries, activeIndex, onSelect }) {
  return (
    <>
      <div className="qlabel">Select a query</div>
      <div className="queries">
        {queries.map((q, i) => (
          <button
            key={q.id}
            className={`qbtn ${i === activeIndex ? 'active' : ''}`}
            onClick={() => onSelect(i)}
          >
            {q.label}
          </button>
        ))}
      </div>
    </>
  );
}