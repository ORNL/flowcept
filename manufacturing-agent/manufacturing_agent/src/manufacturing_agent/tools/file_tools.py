from crewai.tools import BaseTool
import json
from typing import Dict, Any

# In-memory virtual file system
MEM_STORE: Dict[str, Any] = {}

class ReadFileTool(BaseTool):
    name: str = "ReadFileTool"
    description: str = "Reads the content of a file."

    def _run(self, file_path: str) -> str:
        if file_path in MEM_STORE:
            return MEM_STORE[file_path]
        else:
            return f"Error: File not found at path {file_path}"

class WriteFileTool(BaseTool):
    name: str = "WriteFileTool"
    description: str = "Writes content to a file."

    def _run(self, file_path: str, content: str) -> str:
        MEM_STORE[file_path] = content
        return f"File '{file_path}' has been written successfully." 