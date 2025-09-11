import base64
import ast
import io
import json
from pathlib import Path
from importlib.resources import files as pkg_files

import pandas as pd

import streamlit as st
from flowcept.agents.gui import AI
from flowcept.agents import prompt_handler
from flowcept.agents.agent_client import run_tool
from flowcept.agents.agents_utils import ToolResult


from flowcept.agents.gui.audio_utils import _md_to_plain_text, speak
from flowcept.configs import AGENT_AUDIO


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
    if b.startswith(b"%PDF-"):
        return "application/pdf"
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


def _pdf_first_page_to_png(pdf_bytes: bytes, zoom: float = 2.0) -> bytes:
    """
    Convert the first page of a PDF to PNG bytes using PyMuPDF (fitz).
    zoom ~2.0 gives a good thumbnail; increase for higher resolution.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        # PyMuPDF not installed; caller can decide how to handle
        raise ImportError("PyMuPDF (fitz) is required to render PDF thumbnails") from e

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def ensure_data_uri(val):
    r"""Accept bytes/bytearray/memoryview or a repr like "b'\x89PNG...'", or a file path/URL.
    Returns a data URL suitable for st.column_config.ImageColumn. If input is a PDF, converts
    the first page to PNG (requires PyMuPDF).
    """
    # Already a data URI?
    if isinstance(val, str) and val.startswith("data:"):
        return val

    # Bytes repr string? -> real bytes
    if isinstance(val, str) and val.startswith("b'"):
        try:
            val = ast.literal_eval(val)
        except Exception:
            return None

    # Paths that point to a PDF: convert
    if isinstance(val, str) and val.lower().endswith(".pdf") and Path(val).is_file():
        try:
            pdf_bytes = Path(val).read_bytes()
            png_bytes = _pdf_first_page_to_png(pdf_bytes)
            return f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
        except Exception:
            # Fallback: no preview; caller will show blank cell
            return None

    # Normalize to bytes if memoryview/bytearray
    if isinstance(val, memoryview):
        val = val.tobytes()
    if isinstance(val, bytearray):
        val = bytes(val)

    # Raw bytes? detect and convert if PDF
    if isinstance(val, bytes):
        mime = _sniff_mime(val)
        if mime == "application/pdf":
            try:
                png_bytes = _pdf_first_page_to_png(val)
                return f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
            except Exception:
                return None
        # Regular image bytes -> data URI
        return f"data:{mime};base64,{base64.b64encode(val).decode('ascii')}"

    # Otherwise (URL/path to an image) let Streamlit try; PDFs won’t render as images
    return val


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

            if AGENT_AUDIO:
                # 🔊 Speak only if user spoke to us this turn
                print(f"This is the session state nowww: {st.session_state['speak_reply']}")
                if st.session_state.get("speak_reply"):
                    try:
                        plain_text = _md_to_plain_text(summary)
                        print(f"Trying to speak plain text {plain_text}")
                        speak(plain_text)  # uses your existing gTTS-based speak()
                    except Exception as e:
                        st.warning(f"TTS failed: {e}")
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


def _resolve_logo() -> str | None:
    # Try package resource
    try:
        p = pkg_files("flowcept").joinpath("docs/img/flowcept-logo.png")
        if p.is_file():
            return str(p)
    except Exception:
        pass
    # Fallbacks for dev checkouts
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "docs/img/flowcept-logo.png",
        here.parents[2] / "docs/img/flowcept-logo.png",
        here.parents[1] / "docs/img/flowcept-logo.png",
        Path("flowcept/docs/img/flowcept-logo.png"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    print(str(c))
    return None


def resolve_logo_path(package: str = "flowcept", resource: str = "docs/img/flowcept-logo.png") -> str | None:
    """
    Resolve the Flowcept logo whether running from an installed package or a src/ layout repo.
    Returns an absolute string path or None if not found.
    """
    # 1) Try packaged resource (works if docs/img is included in the wheel/sdist)
    try:
        p = pkg_files(package).joinpath(resource)
        if hasattr(p, "is_file") and p.is_file():
            return str(p)
    except Exception:
        pass

    here = Path(__file__).resolve()

    # 2) src/ layout repo: .../<repo>/flowcept/src/flowcept/agents/gui/gui_utils.py
    #    Find the nearest 'src' ancestor, then go to repo root (src/..), then docs/img/...
    try:
        src_dir = next(p for p in here.parents if p.name == "src")
        repo_root = src_dir.parent  # <repo>/flowcept
        cand = repo_root / "docs" / "img" / "flowcept-logo.png"
        if cand.is_file():
            return str(cand)
    except StopIteration:
        pass

    # 3) Editable install package dir: .../src/flowcept (package root)
    pkg_dir = here.parents[2]  # .../src/flowcept
    cand = pkg_dir / "docs" / "img" / "flowcept-logo.png"
    if cand.is_file():
        return str(cand)

    # 4) CWD fallback
    cand = Path.cwd() / "flowcept" / "docs" / "img" / "flowcept-logo.png"
    if cand.is_file():
        return str(cand)

    return None


def render_title_with_logo(
    page_title: str, logo_path: str | None, logo_width: int = 150, add_to_sidebar: bool = True, debug: bool = False
):
    """
    Render a header row with an optional logo next to the title; optionally mirror it in the sidebar.
    """
    if debug:
        st.caption(f"Logo path resolved to: {logo_path or 'NOT FOUND'}")

    if logo_path and Path(logo_path).is_file():
        col_logo, col_title = st.columns([1, 6])
        with col_logo:
            st.image(logo_path, width=logo_width)
        with col_title:
            st.title(page_title)
        if add_to_sidebar:
            st.sidebar.image(logo_path, width=logo_width)
    else:
        st.title(page_title)
