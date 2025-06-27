import io
import json

import streamlit as st
from flowcept.agents import prompt_handler
from flowcept.agents.agent_client import run_tool
from flowcept.agents.agents_utils import ToolResult
import pandas as pd

from flowcept.agents.gui import AI


def query_agent(user_input: str) -> ToolResult:
    try:
        response_str = run_tool(prompt_handler.__name__, kwargs={"message": user_input})[0]
    except Exception as e:
        return ToolResult(code=400, result=f"Failed to communicate with the Agent. Error: {e}")
    try:
        tool_result = ToolResult(**json.loads(response_str))
        if tool_result is None:
            ToolResult(code=404, result=f"Could not parse agent output:\n{response_str}")
        return tool_result
    except Exception as e:
        return ToolResult(code=499, result=f"Failed to parse agent output:\n{response_str}.\n\nError: {e}")


def display_ai_msg(msg: str):
    with st.chat_message("AI", avatar=AI):
        st.markdown(msg)
    return msg


def display_ai_msg_from_tool(tool_result: ToolResult):
    has_error = tool_result.is_error_string()
    with st.chat_message("AI", avatar=AI):
        if has_error:
            agent_reply = (f"❌ Agent encountered an error, code {tool_result.code}:\n\n"
                           f"```text\n{tool_result.result}\n```")
        else:
            agent_reply = tool_result.result

        st.markdown(agent_reply)

    return agent_reply


def display_df_tool_response(tool_result: ToolResult):
    result_dict = tool_result.result
    result_code = result_dict.get("result_code")
    result_df_str = result_dict.get("result_df", "").strip()
    summary = result_dict.get("summary", "")
    summary_error = result_dict.get("summary_error", "")

    plot_code = result_dict.get("plot_code", "")
    with st.chat_message("AI", avatar=AI):

        st.markdown("📊 Here's the code:")
        st.markdown(f"```python\n{result_code}")

        try:
            df = pd.read_csv(io.StringIO(result_df_str))
            print("The result is a df")
            if not df.empty:
                st.dataframe(df, hide_index=False)
                print("Columns", str(df.columns))
                print("Number of columns", len(df.columns))
            else:
                st.text("⚠️ Result DataFrame is empty.")
        except Exception as e:
            st.markdown(f"❌ {e}")
            return

        if plot_code:
            st.markdown("Here's the plot code:")
            st.markdown(f"```python\n{plot_code}")
            st.markdown("📊 Here's the plot:")
            try:
                exec_st_plot_code(plot_code, df, st)
            except Exception as e:
                st.markdown(f"❌ {e}")

        if summary:
            st.markdown("📝 Summary:")
            st.markdown(summary)
        elif summary_error:
            st.markdown(f"⚠️ Encountered this error when summarizing the result dataframe:\n```text\n{summary_error}")


def exec_st_plot_code(code, result_df, st_module):
    print("Plot code \n", code)
    exec(code, {'result': result_df, 'st': st_module, 'plt': __import__('matplotlib.pyplot'), 'alt': __import__('altair')})
