from google import genai
from google.genai import types
import os


class Gemini25LLM:
    """
    Gemini25LLM is a lightweight wrapper around Google's Gemini 2.5 models
    for text generation. It simplifies configuration and provides a unified
    interface for invoking LLM completions with or without streaming.

    Parameters
    ----------
    project_id : str
        Google Cloud project ID for authentication.
    location : str, default="us-east5"
        Vertex AI location where the model is hosted.
    model : str, default="gemini-2.5-flash-lite"
        The Gemini model to use (e.g., "gemini-2.5-flash", "gemini-2.5-pro").
    temperature : float, default=0.7
        Sampling temperature for controlling output randomness.
    top_p : float, default=0.95
        Nucleus sampling parameter; limits tokens to the top cumulative probability.
    max_output_tokens : int, default=2048
        Maximum number of tokens to generate in the response.
    stream : bool, default=False
        Whether to return responses incrementally (streaming) or as a single string.

    Attributes
    ----------
    model_name : str
        Name of the Gemini model used for generation.
    client : genai.Client
        Underlying Google GenAI client instance.
    config : types.GenerateContentConfig
        Default generation configuration for the model.
    stream : bool
        Indicates whether streaming responses are enabled.

    Examples
    --------
    Create a client and run a simple query:

    >>> llm = Gemini25LLM(project_id="my-gcp-project")
    >>> response = llm.invoke("Write a haiku about the ocean.")
    >>> print(response)
    "Blue waves rise and fall / endless dance beneath the sky / whispers of the deep"
    """

    def __init__(
        self,
        project_id: str,
        location: str = "us-east5",
        model: str = "gemini-2.5-flash-lite",
        temperature: float = 0.7,
        top_p: float = 0.95,
        max_output_tokens: int = 2048,
        stream: bool = False,
    ):
        self.model_name = model
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        self.stream = stream
        self.client = genai.Client(vertexai=True, project=project_id, location=location)
        self.config = types.GenerateContentConfig(
            temperature=temperature,
            top_p=top_p,
            max_output_tokens=max_output_tokens,
        )

    def invoke(self, prompt: str, **kwargs) -> str:
        r"""
        Invoke the Gemini LLM with a user prompt.

        This method sends the prompt to the configured Gemini model and returns
        the generated text. It supports both streaming and non-streaming modes.

        Parameters
        ----------
        prompt : str
            The input text prompt to send to the model.
        **kwargs : dict, optional
            Additional arguments (currently unused, kept for extensibility).

        Returns
        -------
        str
            The generated text response from the model. In streaming mode,
            partial outputs are concatenated and returned as a single string.

        Examples
        --------
        Basic invocation:

        >>> llm = Gemini25LLM(project_id="my-gcp-project")
        >>> llm.invoke("Explain quantum entanglement in simple terms.")
        "A phenomenon where particles remain connected so that the state of one..."

        Streaming invocation:

        >>> llm = Gemini25LLM(project_id="my-gcp-project", stream=True)
        >>> llm.invoke("List five creative startup ideas.")
        "1. AI gardening assistant\n2. Virtual museum curator\n..."
        """
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]

        if self.stream:
            stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=self.config,
            )
            return "".join(chunk.text for chunk in stream if chunk.text)
        else:
            result = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=self.config,
            )
            return result.text
