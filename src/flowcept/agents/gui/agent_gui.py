import streamlit as st

from flowcept.agents.gui import AI, PAGE_TITLE
from flowcept.agents.gui.audio_utils import get_audio_text
from flowcept.agents.gui.gui_utils import (
    query_agent,
    display_ai_msg,
    display_ai_msg_from_tool,
    display_df_tool_response,
    resolve_logo_path,
    render_title_with_logo,
)
from flowcept.agents.tools.in_memory_queries.in_memory_queries_tools import (
    generate_result_df,
    generate_plot_code,
    run_df_code,
)
from flowcept.configs import AGENT_AUDIO

# ---- Page setup & header with logo ----
st.set_page_config(page_title=PAGE_TITLE, page_icon=AI)

LOGO_PATH = resolve_logo_path(package="flowcept", resource="docs/img/flowcept-logo.png")
render_title_with_logo(PAGE_TITLE, LOGO_PATH, logo_width=150, add_to_sidebar=False, debug=False)

GREETING = (
    "Hi, there! I'm your **Workflow Provenance Assistant**.\n\n"
    "I am tracking workflow executions and I can:\n"
    "- 🔍 Query running workflows\n"
    "- 📊 Plot graphs\n"
    "- 🤖 Answer general questions about provenance data\n\n"
    "How can I help you today?"
)
display_ai_msg(GREETING)


def main():
    """Main Agent GUI function."""
    st.caption(
        "💡 Quick help\n"
        "Ask about workflow metrics, plots, or summaries.\n\n"
        "I have an internal DataFrame in my context to which you can ask direct questions."
        "Tasks inputs are mapped to `used.*` fields, and outputs to `generated.*`\n"
        "Commands: `@record <note>`; \n `@show records`; \n  `reset context` ; `save context` \n"
        "Tip: Inputs like `result = df[some valid df query]` will run direct queries to the df in context."
    )

    user_input = st.chat_input("Send a message")

    if user_input:
        st.session_state["speak_reply"] = False

    if AGENT_AUDIO:
        user_input = get_audio_text(user_input)

    if user_input:
        with st.chat_message("human"):
            st.markdown(user_input)

        try:
            with st.spinner("🤖 Thinking..."):
                tool_result = query_agent(user_input)

            if tool_result.result_is_str():
                display_ai_msg_from_tool(tool_result)

            elif tool_result.is_success_dict():
                tool_name = tool_result.tool_name
                if tool_name in (
                    generate_result_df.__name__,
                    generate_plot_code.__name__,
                    run_df_code.__name__,
                ):
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
