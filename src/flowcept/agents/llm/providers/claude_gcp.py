import requests


class ClaudeOnGCPLLM:
    """
    ClaudeOnGCPLLM is a wrapper for invoking Anthropic's Claude models
    hosted on Google Cloud Vertex AI. It handles authentication, request
    payload construction, and response parsing for text generation.

    Parameters
    ----------
    project_id : str
        Google Cloud project ID used for Vertex AI requests.
    google_token_auth : str
        Bearer token for Google Cloud authentication.
    location : str, default="us-east5"
        Vertex AI location where the Claude model is hosted.
    model_id : str, default="claude-opus-4"
        Identifier of the Claude model to use.
    anthropic_version : str, default="vertex-2023-10-16"
        API version of Anthropic's Claude model on Vertex AI.
    temperature : float, default=0.5
        Sampling temperature controlling randomness of output.
    max_tokens : int, default=512
        Maximum number of tokens to generate in the response.
    top_p : float, default=0.95
        Nucleus sampling parameter; restricts tokens to a top cumulative probability.
    top_k : int, default=1
        Top-k sampling parameter; restricts tokens to the top-k most likely options.

    Attributes
    ----------
    url : str
        Full REST endpoint URL for the Claude model on Vertex AI.
    headers : dict
        HTTP headers including authentication and content type.
    temperature : float
        Current temperature value used in requests.
    max_tokens : int
        Maximum number of tokens configured for output.
    top_p : float
        Probability cutoff for nucleus sampling.
    top_k : int
        Cutoff for top-k sampling.

    Examples
    --------
    >>> llm = ClaudeOnGCPLLM(project_id="my-gcp-project", google_token_auth="ya29.a0...")
    >>> response = llm.invoke("Write a poem about the sunrise.")
    >>> print(response)
    "A golden light spills across the horizon..."
    """

    def __init__(
        self,
        project_id: str,
        google_token_auth: str,
        location: str = "us-east5",
        model_id: str = "claude-opus-4",
        anthropic_version: str = "vertex-2023-10-16",
        temperature: float = 0.5,
        max_tokens: int = 512,
        top_p: float = 0.95,
        top_k: int = 1,
    ):
        self.project_id = project_id
        self.location = location
        self.model_id = model_id
        self.anthropic_version = anthropic_version
        self.endpoint = f"{location}-aiplatform.googleapis.com"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.top_k = top_k

        self.url = (
            f"https://{self.endpoint}/v1/projects/{self.project_id}/locations/{self.location}"
            f"/publishers/anthropic/models/{self.model_id}:rawPredict"
        )
        self.headers = {
            "Authorization": f"Bearer {google_token_auth}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def invoke(self, prompt: str, **kwargs) -> str:
        """
        Invoke the Claude model with a user prompt.

        This method sends a prompt to the configured Claude model via Google
        Cloud Vertex AI, waits for a response, and returns the generated text.

        Parameters
        ----------
        prompt : str
            The user input to send to the Claude model.
        **kwargs : dict, optional
            Additional keyword arguments (currently unused, kept for extensibility).

        Returns
        -------
        str
            The generated text from the Claude model.

        Raises
        ------
        RuntimeError
            If the Claude API call fails with a non-200 status code.

        Examples
        --------
        >>> llm = ClaudeOnGCPLLM(project_id="my-gcp-project", google_token_auth="ya29.a0...")
        >>> llm.invoke("Summarize the plot of Hamlet in two sentences.")
        "Hamlet seeks to avenge his father’s death, feigns madness, and struggles with indecision.
        Ultimately, nearly all the major characters perish, including Hamlet himself."
        """
        payload = {
            "anthropic_version": self.anthropic_version,
            "stream": False,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
        }

        response = requests.post(self.url, headers=self.headers, json=payload)

        if response.status_code != 200:
            raise RuntimeError(f"Claude request failed: {response.status_code} {response.text}")

        response_json = response.json()

        # Return the text of the first content block
        return response_json["content"][0]["text"]
