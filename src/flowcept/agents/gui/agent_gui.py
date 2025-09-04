import streamlit as st
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

# if "chat_history" not in st.session_state:
#     st.session_state.chat_history = [{"role": "system", "content":GREETING}]
#
# for msg in st.session_state.chat_history:
#     with st.chat_message(msg["role"], avatar=AI):
#         st.markdown(msg["content"])


def main():
    """Main Streamlit Function."""
    user_input = st.chat_input("Send a message")
    st.caption("💡 Tip: Ask about workflow metrics, generate plots, or summarize data.")

    if user_input:
        # st.session_state.chat_history.append({"role": "human", "content": user_input})

        with st.chat_message("human"):
            st.markdown(user_input)

        try:
            with st.spinner("🤖 Thinking..."):
                tool_result = query_agent(user_input)
            print(tool_result)

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
                # display_ai_msg(f"⚠️ Received unexpected response from agent: {tool_result}")
                st.stop()

        except Exception as e:
            display_ai_msg(f"❌ Error talking to MCP agent:\n\n```text\n{e}\n```")
            st.stop()

        # st.session_state.chat_history.append({"role": "system", "content": agent_reply})


main()
