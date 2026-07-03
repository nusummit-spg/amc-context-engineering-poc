export default function RelationshipGraph() {
  return (
    <svg width="100%" height="120" viewBox="0 0 360 120">
      <line x1="60" y1="60" x2="160" y2="30" stroke="#d8c7f5" strokeWidth="2" />
      <line x1="60" y1="60" x2="160" y2="60" stroke="#d8c7f5" strokeWidth="2" />
      <line x1="60" y1="60" x2="160" y2="90" stroke="#d8c7f5" strokeWidth="2" />
      <line x1="160" y1="30" x2="260" y2="45" stroke="#d8c7f5" strokeWidth="2" />
      <line x1="160" y1="60" x2="260" y2="45" stroke="#d8c7f5" strokeWidth="2" />
      <line x1="160" y1="90" x2="260" y2="75" stroke="#d8c7f5" strokeWidth="2" />

      <circle cx="60" cy="60" r="22" fill="#2D2D9F" />
      <text x="60" y="64" textAnchor="middle" fill="white" fontSize="9" fontFamily="Inter" fontWeight="600">Schemes</text>

      <circle cx="160" cy="30" r="16" fill="#7B33C8" />
      <circle cx="160" cy="60" r="16" fill="#7B33C8" />
      <circle cx="160" cy="90" r="16" fill="#7B33C8" />
      <text x="160" y="33" textAnchor="middle" fill="white" fontSize="7.5" fontFamily="Inter">Hold</text>
      <text x="160" y="63" textAnchor="middle" fill="white" fontSize="7.5" fontFamily="Inter">Hold</text>
      <text x="160" y="93" textAnchor="middle" fill="white" fontSize="7.5" fontFamily="Inter">Hold</text>

      <circle cx="260" cy="45" r="20" fill="#0A0A3A" />
      <circle cx="260" cy="75" r="14" fill="#0A0A3A" />
      <text x="260" y="48" textAnchor="middle" fill="white" fontSize="8.5" fontFamily="Inter" fontWeight="600">Adani</text>
      <text x="260" y="78" textAnchor="middle" fill="white" fontSize="7" fontFamily="Inter">Issuer</text>
    </svg>
  );
}