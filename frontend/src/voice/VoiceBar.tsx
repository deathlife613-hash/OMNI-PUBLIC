import { useEffect, useRef, useState } from "react";
import { canListen, canSpeak, listVoices, startListening, stopSpeaking, type Listener } from "./speech";

export interface VoicePrefs {
  speakReplies: boolean;
  voiceURI: string;
  rate: number;
}
const KEY = "omni.voice";
export const loadPrefs = (): VoicePrefs => {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { speakReplies: false, voiceURI: "", rate: 1, ...JSON.parse(raw) };
  } catch {
    /* storage unavailable */
  }
  return { speakReplies: false, voiceURI: "", rate: 1 };
};

interface Props {
  prefs: VoicePrefs;
  onPrefs: (p: VoicePrefs) => void;
  onTranscript: (text: string) => void; // fills the editable message box; never auto-sends
}

export default function VoiceBar({ prefs, onPrefs, onTranscript }: Props) {
  const [listening, setListening] = useState(false);
  const [err, setErr] = useState("");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const ref = useRef<Listener | null>(null);

  useEffect(() => {
    if (!canSpeak()) return;
    const load = () => setVoices(listVoices());
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, []);

  useEffect(() => () => ref.current?.cancel(), []);

  const update = (p: Partial<VoicePrefs>) => {
    const next = { ...prefs, ...p };
    onPrefs(next);
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };

  const start = () => {
    setErr("");
    const l = startListening({
      onText: (t) => onTranscript(t),
      onError: setErr,
      onEnd: () => {
        setListening(false);
        ref.current = null;
      },
    });
    if (l) {
      ref.current = l;
      setListening(true);
    }
  };

  return (
    <div className="voicebar" aria-label="Voice controls">
      {canListen() ? (
        listening ? (
          <>
            <span role="status" className="rec">● Listening…</span>
            <button type="button" onClick={() => ref.current?.stop()}>Done</button>
            <button type="button" onClick={() => ref.current?.cancel()}>Cancel</button>
          </>
        ) : (
          <button type="button" onClick={start} aria-label="Start voice input">🎤 Speak</button>
        )
      ) : (
        <span className="muted">Voice input isn't supported in this browser.</span>
      )}
      {canSpeak() ? (
        <>
          <label className="row">
            <input
              type="checkbox"
              style={{ width: "auto", margin: 0 }}
              checked={prefs.speakReplies}
              onChange={(e) => {
                if (!e.target.checked) stopSpeaking();
                update({ speakReplies: e.target.checked });
              }}
            />
            Read replies aloud
          </label>
          <select aria-label="Voice" value={prefs.voiceURI} onChange={(e) => update({ voiceURI: e.target.value })}>
            <option value="">Default voice</option>
            {voices.map((v) => (
              <option key={v.voiceURI} value={v.voiceURI}>
                {v.name} ({v.lang})
              </option>
            ))}
          </select>
          <label className="row">
            Speed
            <input
              type="range"
              min={0.5}
              max={2}
              step={0.1}
              value={prefs.rate}
              style={{ width: 90, margin: 0 }}
              onChange={(e) => update({ rate: Number(e.target.value) })}
            />
          </label>
          <button type="button" onClick={stopSpeaking}>■ Stop speech</button>
        </>
      ) : (
        <span className="muted">Speech output isn't supported in this browser.</span>
      )}
      {err && <span role="alert" className="error">{err}</span>}
    </div>
  );
}
