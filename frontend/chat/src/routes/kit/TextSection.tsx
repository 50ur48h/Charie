import KitSection from "./KitSection";

const SAMPLE_SQL = `SELECT r.name AS restaurant,
       SUM(o.total - o.tax - o.delivery_fee - o.discount) AS net_sales
FROM orders o
JOIN restaurants r ON r.id = o.restaurant_id
WHERE o.status = 'completed'
  AND r.is_test = false
  AND o.created_at >= '2026-10-01' AND o.created_at < '2026-10-27'
GROUP BY r.name;`;

export default function TextSection() {
  return (
    <KitSection id="text" title="Text">
      <h3 className="page-title">Usage</h3>
      <p className="page-lead">Charie tracks every AI call, so the month&apos;s spending is always known.</p>
      <h3 className="card-title">Most expensive questions</h3>
      <p className="card-sub">Deep questions cost more because Charie digs further</p>
      <h3 className="card-title">Cost per day</h3>
      <p className="card-sub">October, in US dollars</p>
      <p className="field-label">Password</p>
      <p className="field-hint">Stored safely and never shown again.</p>
      <p className="stat-label">Spent this month</p>
      <p className="stat-value">$41.20</p>
      <p className="stat-foot">1–27 Oct</p>
      <p className="prose-text">
        Sales are up 6.2% this month, and people are spending a little more per order.
      </p>
      <p className="text-[13px] text-muted">Replays cost nothing; fresh runs show their price first.</p>
      <pre className="code-block">{SAMPLE_SQL}</pre>
      <p>
        Press <kbd>Enter</kbd> to ask.
      </p>
    </KitSection>
  );
}
