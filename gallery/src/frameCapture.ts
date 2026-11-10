// 1.12.6: stay-on-video after a Vidosser frame capture. Same rules as Media Library:
// ../../frame_capture_rules.js (ReflibFrameCapture). Never navigate to the new frame hash.
import "../../frame_capture_rules.js";

type FC = {
  EVENT: string;
  shouldNavigate: (d: any) => boolean;
  stayHash: (cur: string | null | undefined, d: any) => string | null;
  toastText: (d: any, lang?: string) => string;
  resumePlayback: (was: boolean) => boolean;
  keepOpen: (cur: string | null | undefined, d: any) => { navigate: boolean; hash: string | null; toast: boolean };
  pinFollow: (pin: Pin | null, viewer: number | null, hashAtViewer: string | null | undefined) => Pin | null;
  pinLocate: (pin: Pin | null, viewer: number | null, entries: Iterable<[number, string]>) => { index: number | null; override: boolean; lookup: boolean };
  trackIntent: (el: any) => () => void;
  wantPlay: (el: any, now?: number) => boolean;
};
export type Pin = { hash: string; idx: number };
export const FrameCap: FC = (globalThis as any).ReflibFrameCapture;

/** 1.12.14: play intent = shared ReflibFrameCapture.trackIntent / wantPlay (same code as the Media Library). */
export function trackWantPlay(el: HTMLVideoElement | null | undefined): () => void {
  return FrameCap ? FrameCap.trackIntent(el) : () => {};
}

export function wasWantPlay(el: HTMLVideoElement | null | undefined): boolean {
  if (!el) return false;
  return FrameCap ? FrameCap.wantPlay(el) : !el.paused && !el.ended;
}
