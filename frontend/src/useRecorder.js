import { useCallback, useEffect, useRef, useState } from "react";
import {
  detectRecordingMimeType,
  MAX_DURATION_MS,
  MAX_FILE_BYTES,
  MIN_DURATION_MS,
} from "./recording.js";

function stopTracks(stream) {
  if (!stream) {
    return;
  }
  stream.getTracks().forEach((track) => track.stop());
}

export function useRecorder() {
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [clip, setClip] = useState(null);
  const [mimeType, setMimeType] = useState(() => detectRecordingMimeType());

  const sessionRef = useRef(0);
  const pendingRef = useRef(false);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const maxTimerRef = useRef(null);
  const tickRef = useRef(null);
  const clipUrlRef = useRef(null);

  const clearTimers = useCallback(() => {
    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  const releaseMicrophone = useCallback(() => {
    stopTracks(streamRef.current);
    streamRef.current = null;
  }, []);

  const revokeClipUrl = useCallback(() => {
    if (clipUrlRef.current) {
      URL.revokeObjectURL(clipUrlRef.current);
      clipUrlRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    if (pendingRef.current) {
      pendingRef.current = false;
      sessionRef.current += 1;
      setPhase("idle");
      setElapsedMs(0);
      return;
    }

    clearTimers();
    const recorder = recorderRef.current;
    if (recorder && recorder.state === "recording") {
      recorder.stop();
      return;
    }
    if (recorder) {
      return;
    }

    releaseMicrophone();
  }, [clearTimers, releaseMicrophone]);

  const start = useCallback(async () => {
    const detectedType = detectRecordingMimeType();
    setMimeType(detectedType);

    if (!detectedType) {
      setPhase("unsupported");
      setError("当前浏览器不支持 WebM/Opus 录音，请更换 Chrome 或 Edge。");
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setPhase("error");
      setError("当前页面无法使用麦克风，请使用 localhost 或 HTTPS 访问。");
      return;
    }

    if (pendingRef.current || (recorderRef.current && recorderRef.current.state === "recording")) {
      return;
    }

    sessionRef.current += 1;
    const session = sessionRef.current;
    pendingRef.current = true;
    setError("");
    setElapsedMs(0);
    setPhase("idle");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (session !== sessionRef.current || !pendingRef.current) {
        stopTracks(stream);
        return;
      }

      pendingRef.current = false;
      streamRef.current = stream;
      const chunks = [];
      const recorder = new MediaRecorder(stream, { mimeType: detectedType });
      recorderRef.current = recorder;
      const startedAt = Date.now();

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onerror = () => {
        if (session !== sessionRef.current) {
          return;
        }
        sessionRef.current += 1;
        clearTimers();
        try {
          if (recorder.state !== "inactive") {
            recorder.stop();
          }
        } catch {
          // Recorder may already be stopping.
        }
        recorderRef.current = null;
        releaseMicrophone();
        setPhase("error");
        setError("录制失败，请重试。");
      };

      recorder.onstop = () => {
        recorderRef.current = null;
        clearTimers();
        releaseMicrophone();

        if (session !== sessionRef.current) {
          return;
        }

        const durationMs = Date.now() - startedAt;
        setElapsedMs(Math.min(durationMs, MAX_DURATION_MS));

        if (chunks.length === 0) {
          setPhase("error");
          setError("录制失败，请重试。");
          return;
        }

        const blob = new Blob(chunks, { type: detectedType });
        if (blob.size === 0) {
          setPhase("error");
          setError("录制失败，请重试。");
          return;
        }
        if (durationMs < MIN_DURATION_MS) {
          setPhase("error");
          setError("录音太短，请按住至少 1 秒。");
          return;
        }
        if (blob.size > MAX_FILE_BYTES) {
          setPhase("error");
          setError("录音文件超过 5MB，请缩短录音后重试。");
          return;
        }

        revokeClipUrl();
        const url = URL.createObjectURL(blob);
        clipUrlRef.current = url;
        setClip({
          url,
          blob,
          mimeType: detectedType,
          durationSec: Math.min(durationMs, MAX_DURATION_MS) / 1000,
          size: blob.size,
        });
        setPhase("ready");
        setError("");
      };

      recorder.start(250);
      setPhase("recording");

      tickRef.current = setInterval(() => {
        setElapsedMs(Math.min(Date.now() - startedAt, MAX_DURATION_MS));
      }, 200);

      maxTimerRef.current = setTimeout(() => {
        if (session !== sessionRef.current) {
          return;
        }
        if (recorderRef.current && recorderRef.current.state === "recording") {
          recorderRef.current.stop();
        }
      }, MAX_DURATION_MS);
    } catch (err) {
      pendingRef.current = false;
      if (session !== sessionRef.current) {
        return;
      }
      releaseMicrophone();
      const name = err && err.name ? err.name : "";
      setPhase("error");
      if (name === "NotAllowedError" || name === "PermissionDeniedError") {
        setError("麦克风未授权，请允许浏览器使用麦克风后重试。");
        return;
      }
      if (name === "NotFoundError" || name === "DevicesNotFoundError") {
        setError("未找到可用麦克风，请检查设备后重试。");
        return;
      }
      setError("录制失败，请重试。");
    }
  }, [clearTimers, releaseMicrophone, revokeClipUrl]);

  useEffect(() => {
    return () => {
      sessionRef.current += 1;
      pendingRef.current = false;
      clearTimers();
      const recorder = recorderRef.current;
      recorderRef.current = null;
      if (recorder && recorder.state === "recording") {
        try {
          recorder.stop();
        } catch {
          // Ignore teardown errors.
        }
      }
      releaseMicrophone();
      revokeClipUrl();
    };
  }, [clearTimers, releaseMicrophone, revokeClipUrl]);

  return {
    phase,
    error,
    elapsedMs,
    clip,
    mimeType,
    start,
    stop,
  };
}
