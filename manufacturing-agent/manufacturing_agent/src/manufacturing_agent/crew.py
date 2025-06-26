from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from langchain_core.language_models import LLM

@CrewBase
class ManufacturingAgentCrew():
	"""ManufacturingAgent crew"""
	agents_config = 'config/agents.yaml'
	tasks_config = 'config/tasks.yaml'

	def __init__(self, llm: LLM = None):
		self.llm = llm

	@agent
	def manufacturing_analyst(self) -> Agent:
		return Agent(
			config=self.agents_config['manufacturing_analyst'],
			verbose=True,
			llm=self.llm
		)

	@agent
	def decision_maker(self) -> Agent:
		return Agent(
			config=self.agents_config['decision_maker'],
			verbose=True,
			llm=self.llm
		)

	@agent
	def output_generator(self) -> Agent:
		return Agent(
			config=self.agents_config['output_generator'],
			verbose=True,
			llm=self.llm
		)

	@task
	def analysis_task(self) -> Task:
		return Task(
			config=self.tasks_config['analysis_task'],
			agent=self.manufacturing_analyst()
		)

	@task
	def decision_task(self) -> Task:
		return Task(
			config=self.tasks_config['decision_task'],
			agent=self.decision_maker(),
			context=[self.analysis_task()]
		)

	@task
	def output_task(self) -> Task:
		return Task(
			config=self.tasks_config['output_task'],
			agent=self.output_generator(),
			context=[self.decision_task()]
		)

	@crew
	def crew(self) -> Crew:
		"""Creates the ManufacturingAgent crew"""
		return Crew(
			agents=self.agents, # Automatically created by the @agent decorator
			tasks=self.tasks, # Automatically created by the @task decorator
			process=Process.sequential,
			verbose=True,
		)