import { useEffect, useState } from "react";
import { getHealth } from "./api.js";
import { DEFAULT_CITY } from "./recording.js";
import { CitySelect } from "./components/CitySelect.jsx";
import { HealthStatus } from "./components/HealthStatus.jsx";
import { RecordButton } from "./components/RecordButton.jsx";

export default function App() {
  const [city, setCity] = useState(DEFAULT_CITY);
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState("");

  useEffect(() => {
    getHealth()
      .then((response) => {
        setHealth(response.data);
        setHealthError("");
      })
      .catch(() => {
        setHealth(null);
        setHealthError("无法连接后端健康检查，请确认后端已在 8003 端口启动。");
      });
  }, []);

  return (
    <main className="page">
      <h1>语音约碰面地点</h1>
      <p>按住录音，说出两人位置，查找中间的碰面地点。</p>
      <CitySelect value={city} onChange={setCity} />
      <RecordButton />
      <HealthStatus health={health} error={healthError} />
    </main>
  );
}
