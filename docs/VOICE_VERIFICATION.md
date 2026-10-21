# Verifying voice (needs a human with a microphone)

Voice is browser-native (Web Speech API) in `frontend/src/voice/`. It has **never been run with a real microphone or speakers**; only its pure logic has unit tests (7 vitest tests) and the text UI was shown to work without voice.

## What you must do (about 5 minutes)
Use **desktop Chrome or Edge** on the deployed HTTPS URL (the mic needs HTTPS or localhost). Safari/Firefox support for speech *recognition* is limited or absent - that is expected, not a bug.
1. Open Chat. In the voice bar press the microphone. Browser asks for mic permission: **Allow**. Expected: a clear "Listening" status.
2. Say "what is two plus two". Expected: your words appear in the message box (editable, **not** auto-sent). Edit, then press Send.
3. Press the mic, then **Cancel** before speaking. Expected: stops, nothing is filled in.
4. Block the mic in the browser's site settings, press the mic. Expected: a clear permission error, text chat still works.
5. Turn on speech output, send a message. Expected: the reply is read aloud and stays visible as text. Change voice and speed; press **Stop** mid-sentence. Expected: speech stops immediately.
6. Turn speech output off. Expected: replies are silent.
7. On a long reply, confirm it is read in sections and that Stop halts the remaining sections.

Report each of 1-7 as PASS or FAIL (plus browser and OS). I will record them in `docs/RELEASE_CHECKLIST.md`.

## Not built (do not claim these)
- **Wake word** ("Hey OMNI"): not built. A local detector would need an in-browser model (e.g. openWakeWord/Porcupine WASM), continuous microphone use while the tab is open, and it does not work in background tabs or when a phone sleeps.
- **Local Whisper** speech recognition: not built. Free hosted STT exists on Groq (whisper-large-v3 appeared on the account's model list) but is not wired in; browser recognition may send audio to the browser vendor's servers (Chrome does), which matters for sensitive content.
- No always-on listening; recording only starts when you press the button.
