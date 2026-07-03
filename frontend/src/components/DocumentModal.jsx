import documents from '../data/documents';

const TYPE_ICON = { word: '📝', pdf: '📄', email: '✉️', excel: '📊' };
const TYPE_LABEL = { word: 'Word Document', pdf: 'PDF Document', email: 'Email', excel: 'Excel Workbook' };

export default function DocumentModal({ docId, onClose }) {
  if (!docId) return null;

  const d = documents[docId];
  if (!d) return null;

  function handleBackgroundClick(e) {
    // only close if the click was on the dark overlay itself, not inside the modal card
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <div className="modal-overlay open" onClick={handleBackgroundClick}>
      <div className="modal-doc">
        <div className="doc-titlebar">
          <span className="ic">{TYPE_ICON[d.type]}</span>
          <span className="tname">{d.title}</span>
          <span style={{ fontSize: 10.5, color: 'var(--slate)' }}>{TYPE_LABEL[d.type]}</span>
          <button className="close" onClick={onClose}>✕</button>
        </div>

        {d.type === 'email' && (
          <div className="doc-body email">
            <div className="email-hdr">
              <div><b>From:</b> {d.from}</div>
              <div><b>To:</b> {d.to}</div>
              <div><b>Subject:</b> {d.subject}</div>
              <div><b>Date:</b> {d.date}</div>
            </div>
            <div dangerouslySetInnerHTML={{ __html: d.html }} />
          </div>
        )}

        {d.type === 'excel' && (
          <div className="doc-body excel">
            <table className="xltab">
              <thead>
                <tr>{d.table.headers.map((h, i) => <th key={i}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {d.table.rows.map((row, ri) => (
                  <tr key={ri}>
                    {row.map((cell, ci) => {
                      let cls = '';
                      if (ci === d.table.flagCol) {
                        if (cell === 'Pending' || cell === 'Not reviewed') cls = 'flag-bad';
                        if (cell === 'Compliant') cls = 'flag-good';
                      }
                      return <td className={cls} key={ci}>{cell}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="doc-footer-note" style={{ margin: '14px 20px' }}>
              Tracked manually — no automatic linkage to SEBI circular text or scheme SID content.
            </div>
          </div>
        )}

        {(d.type === 'word' || d.type === 'pdf') && (
          <div className={`doc-body ${d.type}`}>
            <div className="doc-meta-row">
              {d.meta.map((m, i) => <span key={i}>{m}</span>)}
            </div>
            <div dangerouslySetInnerHTML={{ __html: d.html }} />
          </div>
        )}
      </div>
    </div>
  );
}