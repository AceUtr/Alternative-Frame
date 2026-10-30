# D Module Final Acceptance - 2026-10-30

## 1. Full regression

- Command: python -m pytest -q
- Result: 163 passed in 5.73s
- Failed: 0

## 2. Live LLM experiment

- Provider: DeepSeek
- Model: deepseek-v4-pro
- API HTTP status: 200
- Connectivity usage: 9 tokens
- Connectivity latency: 1.222 seconds
- Run ID: real_two_phase_cea1dbeb
- Final status: completed
- Phases: 2
- Failed tasks: 0
- Final acceptance: passed

The first phase failed final acceptance because
FINAL_EVIDENCE.md was missing.

The second phase generated the missing evidence
and passed the acceptance contract.

## 3. Local HTTP performance

- Endpoint: 127.0.0.1:8765/ping
- Requests: 100
- Successful: 100
- Failed: 0
- Mean RTT: 11.0628 ms
- Median RTT: 14.712 ms
- P95 RTT: 16.876 ms
- Maximum RTT: 25.964 ms

Limitation:
This is a localhost HTTP round-trip measurement.
It does not establish cross-device network performance
or Agent end-to-end latency.

## 4. Remaining limitation

Physical multi-device Agent performance has not
been verified because only one device was available.

Raw model execution logs remain local and are
not included in this public report.
