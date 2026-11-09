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
};
export const FrameCap: FC = (globalThis as any).ReflibFrameCapture;

/** Remember whether a <video> was playing; survives Vidosser's brief pause before save. */
export function trackWantPlay(el: HTMLVideoElement | null | undefined): () => void {
  if (!el) return () => {};
  let until = 0;
  const onPlay = () => { until = Number.POSITIVE_INFINITY; (el as any)._reflibWantPlay = true; };
  const onPause = () => { until = performance.now() + 2000; (el as any)._reflibWantPlay = true; };
  el.addEventListener("play", onPlay);
  el.addEventListener("pause", onPause);
  return () => {
    el.removeEventListener("play", onPlay);
    el.removeEventListener("pause", onPause);
    const want = until === Number.POSITIVE_INFINITY || performance.now() < until;
    (el as any)._reflibWantPlay = want;
  };
}

export function wasWantPlay(el: HTMLVideoElement | null | undefined): boolean {
  if (!el) return false;
  if ((el as any)._reflibWantPlay) return true;
  return !el.paused && !el.ended;
}
