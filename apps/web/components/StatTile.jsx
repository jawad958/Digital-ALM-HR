export function StatTile({ label, value, sub, lead }) {
  return (
    <div className={lead ? "stat stat-lead" : "stat"}>
      <div className="stat-l">{label}</div>
      <div className="stat-v num">{value}</div>
      {sub && <div className="stat-s">{sub}</div>}
    </div>
  );
}
