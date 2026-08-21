# Alternative Frame Final Architecture

The system is a centralized Main Agent harness: IntentParser and contract generation define the goal, Planner builds a contract-covered DAG, Orchestrator dispatches role-based child Agents, and GlobalEvaluator decides completion from run-provenanced evidence. LongHorizonController persists phases and delegates recovery to Replanner or LocalDAGRecoveryController.

Communication is bounded: direct DAG dependencies are mandatory context; optional peer results are selected by the Top-k router. Three-layer memory is explicit and auditable: working memory for the current task, episodic memory for phase/event history, and durable memory for promoted contract facts. `events.jsonl` is the append-only trajectory replay source; `state.json` is the resumable state snapshot.

Research and software adapters share frozen `SubTask`, `AgentResult`, `Plan`, `Agent.run()` and `Tool.execute()` contracts. Edge/cloud is a deterministic single-machine runtime simulation with explicit node placement and fallback evidence, not a claim of physical distributed deployment.
