import requests


class ClaudeOnGCPLLM:
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
            "Content-Type": "application/json; charset=utf-8"
        }

    def invoke(self, prompt: str, **kwargs) -> str:
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
        return response_json['content'][0]['text']
