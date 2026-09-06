export const MIN_DURATION_MS = 1000;
export const MAX_DURATION_MS = 60_000;
export const MAX_FILE_BYTES = 5 * 1024 * 1024;
export const DEFAULT_CITY = "杭州";

const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm"];

export function detectRecordingMimeType() {
  if (
    typeof MediaRecorder === "undefined" ||
    typeof MediaRecorder.isTypeSupported !== "function"
  ) {
    return null;
  }

  for (const type of MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }

  return null;
}

export function buildDownloadName(mimeType) {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const extension = mimeType && mimeType.includes("webm") ? "webm" : "webm";
  return `meetup-recording-${stamp}.${extension}`;
}
