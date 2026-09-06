export function HealthStatus({ health, error }) {
  if (error) {
    return <p className="status status-error">{error}</p>;
  }

  if (!health) {
    return <p className="status">正在检查后端…</p>;
  }

  return (
    <p className="status">
      后端状态：{health.data.status}（request_id：{health.request_id}）
    </p>
  );
}
