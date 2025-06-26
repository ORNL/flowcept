This simple example shows communication between two agents through Flowcept's provenance messages.

### Setup:

- Agent1 runs on localhost:8000
- Agent2 runs on localhost:8001
- Client talks to agent1

### Running

1. Run Agent1
2. Run Agent2
3. Activate agent2 (this step has to be skipped but couldn't find out how yet): curl -X POST http://localhost:8001/mcp/agent/Agent2/action/liveness      -H "Content-Type: application/json"

The sequence begins by running

`flowcept --agent-client --tool-name  agent_task1`

### Sequence of Message Passing

1. Client starts by calling Agent 1's tool: agent_task1
2. Instrumented Agent Action agent_task1 sends its completion message 
3. Agent 1 sends "call_agent_task" message to call agent_task2
4. Agent 2 receives it
5. Agent 2 runs its tool agent_task2
6. Instrumented Agent Action agent_task2 sends its completion message (subtype 'agent_task')
7. Agent 1 receives it. Prints and finishes.
