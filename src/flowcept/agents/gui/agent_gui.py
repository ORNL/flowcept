from io import BytesIO
import base64

import streamlit as st
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from pydub import AudioSegment  # needs ffmpeg installed

from flowcept.agents.gui import AI, PAGE_TITLE
from flowcept.agents.gui.gui_utils import (
    query_agent,
    display_ai_msg,
    display_ai_msg_from_tool,
    display_df_tool_response,
)
from flowcept.agents.tools.in_memory_queries.in_memory_queries_tools import (
    generate_result_df,
    generate_plot_code,
    run_df_code,
)

# ---------------------- Streamlit page ----------------------
st.set_page_config(page_title=PAGE_TITLE, page_icon=AI)
st.title(PAGE_TITLE)

GREETING = (
    "Hi, there! I'm a **Workflow Provenance Specialist**.\n\n"
    "I am tracking workflow executions and I can:\n"
    "- 🔍 Analyze running workflows\n"
    "- 📊 Plot graphs\n"
    "- 🤖 Answer general questions about provenance data\n\n"
    "How can I help you today?"
)
display_ai_msg(GREETING)

# ---------------------- Audio helpers ----------------------
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
    seg = AudioSegment.from_file(BytesIO(blob))           # ffmpeg does the heavy lifting
    seg = seg.set_channels(1).set_frame_rate(16000).set_sample_width(2)
    buf = BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()

# ---------------------- Main app ----------------------
def main():
    st.caption("💡 Tip: Ask about workflow metrics, generate plots, or summarize data.")
    user_input = st.chat_input("Send a message")
    # If user typed, do not speak back this turn
    if user_input:
        st.session_state["speak_reply"] = False

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
                        print(f"Setting session state to {st.session_state['speak_reply'] }")
                except Exception as e:
                    st.warning(f"Transcription failed: {e}")

    if user_input:
        with st.chat_message("human"):
            st.markdown(user_input)

        try:
            with st.spinner("🤖 Thinking..."):
                tool_result = query_agent(user_input)
            # print(tool_result)  # optional debug

            if tool_result.result_is_str():
                display_ai_msg_from_tool(tool_result)

            elif tool_result.is_success_dict():
                tool_name = tool_result.tool_name
                if tool_name in [generate_result_df.__name__, generate_plot_code.__name__, run_df_code.__name__]:
                    display_df_tool_response(tool_result)
                else:
                    display_ai_msg(f"⚠️ Received unexpected response from agent: {tool_result}")
                    st.stop()
            else:
                display_df_tool_response(tool_result)
                st.stop()

        except Exception as e:
            display_ai_msg(f"❌ Error talking to MCP agent:\n\n```text\n{e}\n```")
            st.stop()

if "speak_reply" not in st.session_state:
    st.session_state["speak_reply"] = False
main()
