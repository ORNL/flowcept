import base64
import ast
import io
import json

import streamlit as st
from flowcept.agents import prompt_handler
from flowcept.agents.agent_client import run_tool
from flowcept.agents.agents_utils import ToolResult
import pandas as pd

from flowcept.agents.gui import AI


def query_agent(user_input: str) -> ToolResult:
    """
    Send a user query to the agent and parse the response.

    This function forwards the user input to the registered prompt handler
    via ``run_tool``. The raw string response is then parsed into a
    ``ToolResult`` for structured handling of success and error cases.

    Parameters
    ----------
    user_input : str
        The text query provided by the user.

    Returns
    -------
    ToolResult
        - ``code=400`` if the agent call fails.
        - ``code=404`` if the agent response could not be parsed.
        - ``code=499`` if JSON parsing fails.
        - Otherwise, the parsed ``ToolResult`` object from the agent.

    Examples
    --------
    >>> result = query_agent("Summarize the latest report.")
    >>> if result.is_success():
    ...     print(result.result)
    """
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
    """
    Display an AI message in the Streamlit chat interface.

    This function creates a new chat message block with the "AI" role and
    renders the given string as Markdown.

    Parameters
    ----------
    msg : str
        The AI message to display.

    Returns
    -------
    str
        The same message string, useful for chaining or logging.

    Examples
    --------
    >>> display_ai_msg("Hello! How can I help you today?")
    """
    with st.chat_message("AI", avatar=AI):
        st.markdown(msg)
    return msg


def display_ai_msg_from_tool(tool_result: ToolResult):
    """
    Display an AI message based on a ToolResult.

    This function inspects the ``ToolResult`` to determine whether it
    represents an error or a normal response. It then displays the
    corresponding message in the Streamlit chat with the "AI" role.

    Parameters
    ----------
    tool_result : ToolResult
        The tool result containing the agent's reply or error.

    Returns
    -------
    str
        The final message displayed in the chat.

    Notes
    -----
    - If the result indicates an error (4xx codes), the message is shown in
      a formatted error block with the error code.
    - Otherwise, the raw result is displayed as Markdown.

    Examples
    --------
    >>> res = ToolResult(code=301, result="Here is the summary you requested.")
    >>> display_ai_msg_from_tool(res)

    >>> err = ToolResult(code=405, result="Invalid JSON response")
    >>> display_ai_msg_from_tool(err)
    """
    has_error = tool_result.is_error_string()
    with st.chat_message("AI", avatar=AI):
        if has_error:
            agent_reply = (
                f"❌ Agent encountered an error, code {tool_result.code}:\n\n```text\n{tool_result.result}\n```"
            )
        else:
            agent_reply = tool_result.result

        st.markdown(agent_reply)

    return agent_reply


def _sniff_mime(b: bytes) -> str:
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if b.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if b.startswith(b"GIF87a") or b.startswith(b"GIF89a"):
        return "image/gif"
    if b.startswith(b"BM"):
        return "image/bmp"
    if b.startswith(b"RIFF") and b[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def ensure_data_uri(val):
    r"""Accepts bytes/bytearray/memoryview or a repr like \"b'\\x89PNG...'\" and returns a data URL."""
    if isinstance(val, str) and val.startswith("data:"):
        return val
    if isinstance(val, str) and val.startswith("b'"):
        try:
            val = ast.literal_eval(val)  # turn repr into bytes
        except Exception:
            return None
    if isinstance(val, memoryview):
        val = val.tobytes()
    if isinstance(val, bytearray):
        val = bytes(val)
    if isinstance(val, bytes):
        mime = _sniff_mime(val)
        return f"data:{mime};base64,{base64.b64encode(val).decode('ascii')}"
    return val  # path/URL, etc.


def _render_df(df: pd.DataFrame, image_width: int = 90, row_height: int = 90):
    if "image" in df.columns:
        df = df.copy()
        df["image"] = df["image"].apply(ensure_data_uri)
        st.dataframe(
            df,
            column_config={"image": st.column_config.ImageColumn("Preview", width=image_width)},
            hide_index=True,
            row_height=row_height,  # make thumbnails visible
        )
    else:
        st.dataframe(df, hide_index=True)


def display_df_tool_response(tool_result: ToolResult):
    r"""
    Display the DataFrame contained in a ToolResult.

    This function extracts and displays the DataFrame (if present) from a
    ``ToolResult`` object, typically after executing a query or code
    generation tool. It is intended for interactive use in environments
    where DataFrame output should be visualized or printed.

    Parameters
    ----------
    tool_result : ToolResult
        The tool result object containing the output of a previous operation.
        Expected to include a CSV-formatted DataFrame string in its ``result``
        field when ``code`` indicates success.

    Notes
    -----
    - If the result does not contain a DataFrame, the function may print or
      display an error message.
    - The display method may vary depending on the environment (e.g., console,
      Streamlit, or notebook).

    Examples
    --------
    >>> result = ToolResult(code=301, result={"result_df": "col1,col2\\n1,2\\n3,4"})
    >>> display_df_tool_response(result)
    col1  col2
    0     1     2
    1     3     4
    """
    result_dict = tool_result.result
    result_code = result_dict.get("result_code", "")
    result_df_str = result_dict.get("result_df", "").strip()

    summary = result_dict.get("summary", "")
    summary_error = result_dict.get("summary_error", "")

    plot_code = result_dict.get("plot_code", "")
    with st.chat_message("AI", avatar=AI):
        st.markdown("📊 Here's the code:")
        st.markdown(f"```python\n{result_code}")
        print(result_code)

        try:
            df = pd.read_csv(io.StringIO(result_df_str))
            print("The result is a df")
            if not df.empty:
                _render_df(df)

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
            print(f"THIS IS THE SUMMARY\n{summary}")
            st.markdown(summary)
        elif summary_error:
            st.markdown(f"⚠️ Encountered this error when summarizing the result dataframe:\n```text\n{summary_error}")


def exec_st_plot_code(code, result_df, st_module):
    """
    Execute plotting code dynamically with a given DataFrame and plotting modules.

    This function runs a block of Python code (typically generated by an LLM)
    to produce visualizations. It injects the provided DataFrame and plotting
    libraries into the execution context, allowing the code to reference them
    directly.

    Parameters
    ----------
    code : str
        The Python code to execute, expected to contain plotting logic.
    result_df : pandas.DataFrame
        The DataFrame to be used within the plotting code (available as ``result``).
    st_module : module
        The Streamlit module (``st``) to be used within the plotting code.

    Notes
    -----
    - The execution context includes:
      - ``result`` : the provided DataFrame.
      - ``st`` : the given Streamlit module.
      - ``plt`` : ``matplotlib.pyplot`` for standard plotting.
      - ``alt`` : ``altair`` for declarative plotting.
    - The function uses Python's built-in ``exec``; malformed or unsafe code
      may raise exceptions or cause side effects.
    - Designed primarily for controlled scenarios such as running generated
      plotting code inside an application.

    Examples
    --------
    >>> import streamlit as st
    >>> df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    >>> code = "st.line_chart(result)"
    >>> exec_st_plot_code(code, df, st)
    """
    print("Plot code \n", code)
    exec(
        code,
        {"result": result_df, "st": st_module, "plt": __import__("matplotlib.pyplot"), "alt": __import__("altair")},
    )
