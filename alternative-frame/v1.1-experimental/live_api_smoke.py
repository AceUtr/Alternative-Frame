"""Real low-cost OpenAI-compatible API smoke test using this project's own client.
Never stores API keys or raw prompt responses in the evidence JSON.
"""
import json
import os
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

from core.model_client import ModelConfig, OpenAICompatibleClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('live_api_smoke_evidence.json'))
    args = parser.parse_args()
    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    if not os.environ.get('MODEL_API_KEY') or not os.environ.get('MODEL_NAME'):
        print('Missing MODEL_API_KEY or MODEL_NAME; no request sent', file=sys.stderr)
        return 2
    config = ModelConfig.from_env()
    config.max_tokens = min(config.max_tokens, 128)
    config.timeout_seconds = 45
    start = time.perf_counter()
    evidence = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'test_type': 'real_api_connectivity_smoke',
        'model': config.model,
        'real_api': True,
        'note': 'Connectivity only; not a multi-Agent performance benchmark.',
    }
    try:
        message = OpenAICompatibleClient(config).chat([
            {'role': 'user', 'content': 'Reply with the single word OK.'}
        ], max_attempts=1)
        content = message.get('content') or ''
        evidence.update({
            'outcome': 'success' if bool(content.strip()) else 'empty_response',
            'latency_seconds': round(time.perf_counter()-start, 3),
            'has_content': bool(content.strip()),
            'finish_reason': message.get('_finish_reason'),
            'usage': message.get('_usage', None),
            'usage_status': 'reported' if message.get('_usage') else 'unknown',
        })
    except Exception as exc:
        # Do not write raw exceptions because upstream gateways may echo URL/token data.
        evidence.update({
            'outcome': 'error',
            'latency_seconds': round(time.perf_counter()-start, 3),
            'error_type': type(exc).__name__,
            'note': 'Error details not saved to avoid accidental credential leakage.',
        })
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Outcome:', evidence['outcome'], '| evidence:', out.resolve())
    return 0 if evidence['outcome'] == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
