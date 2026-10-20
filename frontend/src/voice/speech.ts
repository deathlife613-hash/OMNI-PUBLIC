// Voice module. Fully separate from chat: if anything here fails, text chat still works.
// Uses browser-native Web Speech APIs (no server, no cost). Support varies by browser:
// speech recognition is mainly Chromium/Safari and some engines send audio to the vendor's servers.

/* eslint-disable @typescript-eslint/no-explicit-any */
const SR: any =
  typeof window !== "undefined" ? (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition : undefined;

export const canListen = (): boolean => !!SR;
export const canSpeak = (): boolean => typeof window !== "undefined" && "speechSynthesis" in window;

/** Splits long text into sentence-aligned chunks no longer than `max` chars. */
export function chunkText(text: string, max = 220): string[] {
  const clean = text.replace(/```[\s\S]*?```/g, " (code block omitted) ").replace(/[*_`#>]/g, "").trim();
  if (!clean) return [];
  const sentences = clean.match(/[^.!?\n]+[.!?]*\s*/g) ?? [clean];
  const out: string[] = [];
  let cur = "";
  for (const s of sentences) {
    if (s.length > max) {
      if (cur.trim()) out.push(cur.trim());
      cur = "";
      for (let i = 0; i < s.length; i += max) out.push(s.slice(i, i + max).trim());
    } else if ((cur + s).length > max) {
      out.push(cur.trim());
      cur = s;
    } else cur += s;
  }
  if (cur.trim()) out.push(cur.trim());
  return out.filter(Boolean);
}

export function listenErrorMessage(code: string): string {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone permission was denied. Allow microphone access for this site in your browser settings.";
    case "no-speech":
      return "No speech was detected. Try again.";
    case "audio-capture":
      return "No microphone was found.";
    case "network":
      return "Speech recognition needs a network connection in this browser.";
    case "aborted":
      return "";
    default:
      return `Speech recognition failed (${code}).`;
  }
}

export interface Listener {
  stop: () => void; // finish and deliver what was heard
  cancel: () => void; // discard
}

/** Starts one explicit recording session (never continuous/background). */
export function startListening(h: {
  onText: (text: string, final: boolean) => void;
  onError: (message: string) => void;
  onEnd: () => void;
}): Listener | null {
  if (!SR) return null;
  const rec = new SR();
  rec.lang = navigator.language || "en-US";
  rec.interimResults = true;
  rec.continuous = false;
  let cancelled = false;
  rec.onresult = (e: any) => {
    if (cancelled) return;
    let text = "";
    let final = false;
    for (let i = 0; i < e.results.length; i++) {
      text += e.results[i][0].transcript;
      final = e.results[i].isFinal;
    }
    h.onText(text, final);
  };
  rec.onerror = (e: any) => {
    const m = listenErrorMessage(e.error);
    if (m && !cancelled) h.onError(m);
  };
  rec.onend = () => h.onEnd();
  try {
    rec.start();
  } catch {
    h.onError("Could not start the microphone.");
    return null;
  }
  return {
    stop: () => rec.stop(),
    cancel: () => {
      cancelled = true;
      rec.abort();
    },
  };
}

export const listVoices = (): SpeechSynthesisVoice[] => (canSpeak() ? window.speechSynthesis.getVoices() : []);

let token = 0;
/** Reads text in sections; returns after starting. `stopSpeaking()` halts immediately. */
export function speak(text: string, opts: { voiceURI?: string; rate?: number; onEnd?: () => void; onError?: () => void }): void {
  if (!canSpeak()) {
    opts.onError?.();
    return;
  }
  stopSpeaking();
  const my = ++token;
  const parts = chunkText(text);
  const voice = listVoices().find((v) => v.voiceURI === opts.voiceURI);
  const next = (i: number) => {
    if (my !== token) return;
    if (i >= parts.length) {
      opts.onEnd?.();
      return;
    }
    const u = new SpeechSynthesisUtterance(parts[i]);
    if (voice) u.voice = voice;
    u.rate = Math.min(2, Math.max(0.5, opts.rate ?? 1));
    u.onend = () => next(i + 1);
    u.onerror = () => {
      if (my === token) opts.onError?.();
    };
    window.speechSynthesis.speak(u);
  };
  next(0);
}

export function stopSpeaking(): void {
  token++;
  if (canSpeak()) window.speechSynthesis.cancel();
}
