import re
import tempfile
from io import BytesIO
import base64

import streamlit as st
from gtts import gTTS
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from pydub import AudioSegment  # needs ffmpeg installed


def _normalize_mic_output(out) -> bytes | None:
    """Handle different return shapes from streamlit-mic-recorder."""
    if not isinstance(out, dict):
        return None
    if out.get("wav"):
        return out["wav"]
    if out.get("bytes"):
        return out["bytes"]
    if out.get("b64"):
        return base64.b64decode(out["b64"])
    return None


def _is_wav_pcm(blob: bytes) -> bool:
    """Quick RIFF/WAVE header check."""
    h = blob[:12]
    return h.startswith(b"RIFF") and h[8:12] == b"WAVE"


def _to_pcm_wav_16k(blob: bytes) -> bytes:
    """
    Convert arbitrary audio bytes (webm/ogg/mp3/…) to 16-bit PCM WAV mono @16k.
    Requires ffmpeg via pydub.
    """
    if _is_wav_pcm(blob):
        return blob
    seg = AudioSegment.from_file(BytesIO(blob))  # ffmpeg does the heavy lifting
    seg = seg.set_channels(1).set_frame_rate(16000).set_sample_width(2)
    buf = BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()


def get_audio_text(user_input: str) -> str:
    """
    User Audio Getter.
    """
    # Voice input expander
    with st.expander("🎤 Voice input", expanded=False):
        st.caption("Click **Speak**, talk, then **Stop**. Allow mic permission in your browser.")
        out = mic_recorder(
            start_prompt="🎙️ Speak",
            stop_prompt="⏹️ Stop",
            key="mic_rec_1",
            use_container_width=True,
        )

        # Normalize outputs from the component
        raw_audio = _normalize_mic_output(out)

        if raw_audio:
            try:
                wav_bytes = _to_pcm_wav_16k(raw_audio)
            except Exception as e:
                st.error(f"Could not convert audio to WAV (need ffmpeg/ffprobe?): {e}")
                wav_bytes = None

            if wav_bytes:
                st.audio(wav_bytes, format="audio/wav")

                # Transcribe with SpeechRecognition
                r = sr.Recognizer()
                try:
                    with sr.AudioFile(BytesIO(wav_bytes)) as source:
                        audio = r.record(source)
                    voice_text = r.recognize_google(audio)  # type: ignore[attr-defined]
                    st.success(f"You said: {voice_text}")
                    if not user_input:
                        user_input = voice_text
                        st.session_state["speak_reply"] = True  # speak back only when voice was used
                        print(f"Setting session state to {st.session_state['speak_reply']}")
                except Exception as e:
                    st.warning(f"Transcription failed: {e}")

    return user_input


def speech_to_text():
    """Record from mic, return transcribed text or None."""
    rec = mic_recorder(
        start_prompt="🎙️ Speak",
        stop_prompt="⏹️ Stop",
        key="mic",
        use_container_width=True,
    )
    if rec and "wav" in rec:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(rec["wav"])
            tmp.flush()
            r = sr.Recognizer()
            with sr.AudioFile(tmp.name) as source:
                audio = r.record(source)
            try:
                return r.recognize_google(audio)
            except Exception as e:
                st.warning(f"Speech recognition failed: {e}")
    return None


def speak(text: str):
    """Synthesize speech for the agent reply and play it."""
    if not text:
        return
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            gTTS(text).save(tmp.name)
            st.audio(tmp.name, format="audio/mp3")
    except Exception as e:
        st.warning(f"TTS failed: {e}")


def _md_to_plain_text(s: str) -> str:
    """Very light Markdown cleanup for TTS."""
    s = re.sub(r"```.*?```", lambda m: m.group(0).replace("```", ""), s, flags=re.S)  # drop fences
    s = s.replace("`", "")  # inline code ticks
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # links: [text](url) -> text
    return s.strip()
