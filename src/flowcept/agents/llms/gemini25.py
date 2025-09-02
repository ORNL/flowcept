from google import genai
from google.genai import types
import os


class Gemini25LLM:
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
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)]
            )
        ]

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
