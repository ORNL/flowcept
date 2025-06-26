from crewai.tools import BaseTool

class HumanInputTool(BaseTool):
    name: str = "human_input"
    description: str = "Asks for human input. The human may or may not provide feedback."
    
    def _run(self) -> str:
        return input("Please provide your feedback or press Enter to continue: ") 