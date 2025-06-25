import io
import json

import streamlit as st
from flowcept.flowceptor.agents.agent_client import run_tool
import pandas as pd

DEFAULT_AGENT_NAME = "FlowceptAgent"

st.set_page_config(page_title="Flowcept Agent Chat", page_icon="🤖")
st.title("Flowcept Agent Chat")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [{"role": "system", "content": "Hi, there! What's up?"}]

user_input = st.chat_input("Send a message")

# # Display chat history
# for msg in st.session_state.chat_history:
#     with st.chat_message(msg["role"]):
#         st.markdown(msg["content"])

# Process user input
if user_input:
    st.session_state.chat_history.append({"role": "human", "content": user_input})
    with st.chat_message("human"):
        st.markdown(user_input)

    try:
        agent_response_str = run_tool(tool_name="prompt_handler", kwargs={"message": user_input})[0]

        try:
            agent_response = json.loads(agent_response_str)
        except Exception as e:
            agent_response = agent_response_str
            pass

        print(agent_response)

        if isinstance(agent_response, str):
            print("response is str")
            agent_reply = agent_response
            with st.chat_message("system"):
                st.markdown(agent_reply)

        elif isinstance(agent_response, dict):
            print("response is dict")
            # Dictionary response from the agent
            error = agent_response.get("error")

            if error:
                agent_reply = f"❌ Agent encountered an error:\n\n```text\n{error}\n```"
                with st.chat_message("system"):
                    st.markdown(agent_reply)
            else:
                code = agent_response.get("code", "")
                result = agent_response.get("result", "")
                summary = agent_response.get("summary", "")
                msg_only = agent_response.get("msg_only", True)
                print("Raw result:")
                print(result)
                print("\n\n")

                if msg_only and result:
                    agent_reply = result
                    with st.chat_message("system"):
                        st.markdown(agent_reply)

                else:

                    with st.chat_message("system"):
                        st.markdown("✅ This was the code I ran:")
                        st.code(code, language="python")

                        st.markdown("📊 Here's the result:")

                        if isinstance(result, pd.DataFrame):
                            st.dataframe(result)

                        elif isinstance(result, str):
                            result_str = result.strip()

                            try:
                                # Try parsing it as a CSV (covers multi-row DataFrame as string)
                                df = pd.read_csv(io.StringIO(result_str))
                                print("The result is a df")
                                if not df.empty:
                                    st.dataframe(df, hide_index=False)
                                    print("Columns", str(df.columns))
                                    print("Number of columns", len(df.columns))
                                else:
                                    st.text("Result DataFrame is empty")
                            except Exception as e:
                                st.text(e)

                        else:
                            st.text(str(result))

                        if summary:
                            st.markdown("📝 Summary:")
                            st.markdown(summary)

                    agent_reply = f"Ran code:\n```python\n{code}\n```\n\nResult:\n{result}\n\nSummary:\n{summary}"
        else:
            agent_reply = "⚠️ Received unexpected response format from agent."

    except Exception as e:
        agent_reply = f"❌ Error talking to MCP agent:\n\n```text\n{e}\n```"
        with st.chat_message("system"):
            st.markdown(agent_reply)

    # Store last agent reply to history (even if already rendered)
    st.session_state.chat_history.append({"role": "system", "content": agent_reply})
