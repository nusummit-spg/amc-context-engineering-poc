import { isValidElement } from "react";

function cellContent(value) {
  if (isValidElement(value)) return value;
  return String(value ?? "");
}

export default function DataFrame({ columns, rows, showIndex = true, maxHeight = 320 }) {
  return (
    <div className="stDataFrameWrap" style={{ maxHeight }}>
      <table className="stDataFrame">
        <thead>
          <tr>
            {showIndex && <th className="idx"></th>}
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {showIndex && <td className="idx">{i}</td>}
              {columns.map((c) => (
                <td key={c} style={isValidElement(row[c]) ? { textAlign: "center" } : undefined}>
                  {cellContent(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
