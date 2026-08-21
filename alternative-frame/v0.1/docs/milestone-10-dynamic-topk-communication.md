# Milestone 10: Dynamic Top-k Communication MVP

## Purpose

The centralized Main Agent previously passed every completed `AgentResult` to every later Agent. That is auditable but causes irrelevant context to grow with long-horizon task length.

`TopKCommunicationRouter` now builds a dynamic, task-specific communication topology without changing the frozen `Agent.run(SubTask, context)` interface.

## Routing Rules

1. Direct DAG dependencies are contractual context and are always delivered.
2. Other completed Agent results are optional peer messages.
3. Optional peers are scored by matching input artifacts, preferred roles, topic overlap and successful status.
4. Only the highest-scoring `communication_top_k` optional peers are delivered.
5. Ties are resolved by stable task ID ordering.
6. `communication_top_k` is bounded between 0 and 8 and fails closed when invalid.

The routing decision records the receiver, mandatory dependency senders, selected peer senders, all candidate scores and reasons. Callers can persist it through `on_communication_event`.

## Explicit Boundary

This is dynamic sparse communication under Main Agent control. It is not unrestricted Agent-to-Agent chat, learned routing, shared mutable memory or decentralized consensus. Tool permissions and contractual DAG dependencies remain unchanged.

## Usage

```python
router = TopKCommunicationRouter(default_top_k=2)
orchestrator = Orchestrator(
    registry,
    communication_router=router,
    on_communication_event=record_event,
)
```

Individual tasks may set:

```python
metadata={
    "communication_top_k": 2,
    "communication_topics": ["JWT", "security"],
    "communication_roles": ["reviewer", "architect"],
}
```

Default Orchestrator behavior is unchanged when no communication router is supplied.
