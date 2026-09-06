import { useEffect, useMemo } from "react";
import { buildDownloadName } from "../recording.js";
import { useRecorder } from "../useRecorder.js";

function formatSeconds(ms) {
  return (ms / 1000).toFixed(1);
}

function formatBytes(size) {
  if (size < 1024) {
    return `${size} B`;
  }
  return `${(size / 1024).toFixed(1)} KB`;
}

export function RecordButton() {
  const { phase, error, elapsedMs, clip, mimeType, start, stop } = useRecorder();

  const downloadName = useMemo(() => {
    if (!clip) {
      return "";
    }
    return buildDownloadName(clip.mimeType);
  }, [clip]);

  useEffect(() => {
    if (phase !== "recording") {
      return undefined;
    }

    function endFromWindow(event) {
      if (event.type === "pointerup" && event.button !== undefined && event.button !== 0) {
        return;
      }
      stop();
    }

    window.addEventListener("pointerup", endFromWindow);
    window.addEventListener("pointercancel", endFromWindow);
    return () => {
      window.removeEventListener("pointerup", endFromWindow);
      window.removeEventListener("pointercancel", endFromWindow);
    };
  }, [phase, stop]);

  function handlePointerDown(event) {
    if (event.button !== undefined && event.button !== 0) {
      return;
    }
    event.preventDefault();
    if (phase === "unsupported") {
      return;
    }
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture is best-effort; window-level pointerup still ends recording.
    }
    start();
  }

  function handlePointerEnd(event) {
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    stop();
  }

  return (
    <section className="recorder">
      <button
        type="button"
        className={phase === "recording" ? "record-button recording" : "record-button"}
        disabled={phase === "unsupported"}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
        onContextMenu={(event) => event.preventDefault()}
      >
        {phase === "recording" ? "松开结束" : "按住说话"}
      </button>

      {phase === "recording" ? (
        <p className="status">录音中 {formatSeconds(elapsedMs)} 秒</p>
      ) : null}

      {phase === "unsupported" || error ? (
        <p className="status status-error">{error}</p>
      ) : null}

      {phase === "ready" && clip ? (
        <div className="clip">
          <p className="status">
            录音完成，可本地试听。格式 {clip.mimeType}，约 {clip.durationSec.toFixed(1)}{" "}
            秒，{formatBytes(clip.size)}。
          </p>
          <audio controls src={clip.url} />
          <a className="download" href={clip.url} download={downloadName}>
            下载录音（临时，供后续上传接口测试）
          </a>
        </div>
      ) : null}

      {phase === "idle" && mimeType ? (
        <p className="hint">将使用 {mimeType} 录音，时长 1—60 秒，文件不超过 5MB。</p>
      ) : null}
    </section>
  );
}
