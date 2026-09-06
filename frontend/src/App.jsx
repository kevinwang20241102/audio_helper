import { useEffect, useState } from "react";
import { getHealth } from "./api.js";
import { HealthStatus } from "./components/HealthStatus.jsx";

export default function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getHealth()
      .then((response) => {
        setHealth(response.data);
        setError("");
      })
      .catch(() => {
        setHealth(null);
        setError("无法连接后端健康检查，请确认后端已在 8003 端口启动。");
      });
  }, []);

  return (
    <main className="page">
      <h1>语音约碰面地点</h1>
      <p>按住录音，说出两人位置，查找中间的碰面地点。</p>
      <HealthStatus health={health} error={error} />
    </main>
  );
}
