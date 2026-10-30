"""Minimal DeepSeek/OpenAI-compatible connectivity check. Never saves credentials."""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('live_api_diagnostic_evidence.json')
base = os.environ.get('MODEL_BASE_URL', '').strip().rstrip('/')
model = os.environ.get('MODEL_NAME', '').strip()
key = os.environ.get('MODEL_API_KEY', '').strip()
result = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'test_type': 'live_api_diagnostic', 'model': model, 'outcome': 'error', 'real_api': False}
start = time.monotonic()
try:
    if not base.startswith('https://'):
        raise ValueError('BASE_URL_MUST_BE_HTTPS')
    if not key or not model:
        raise ValueError('MISSING_MODEL_OR_KEY')
    if base.endswith('/chat/completions'):
        url = base
    elif base.endswith('/v1'):
        url = base + '/chat/completions'
    else:
        url = base + '/chat/completions'
    body = {'model': model, 'messages': [{'role': 'user', 'content': 'Say OK.'}], 'max_tokens': 64, 'stream': False, 'thinking': {'type': 'disabled'}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key}, method='POST')
    result['real_api'] = True
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            data = json.load(response)
            result['http_status'] = response.status
        result['outcome'] = 'success' if data.get('choices') else 'invalid_response'
        usage = data.get('usage')
        if isinstance(usage, dict):
            result['usage'] = {k: usage[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens') if isinstance(usage.get(k), int)}
    except urllib.error.HTTPError as exc:
        result['http_status'] = exc.code
        result['error_type'] = 'HTTPError'
        result['error_hint'] = ('authentication' if exc.code in (401,403) else 'billing' if exc.code == 402 else 'request_or_model' if exc.code in (400,404,422) else 'rate_limit' if exc.code == 429 else 'server_error' if exc.code >= 500 else 'other_http')
    except urllib.error.URLError as exc:
        result['error_type'] = 'URLError'
        result['error_hint'] = 'network_or_tls'
    except TimeoutError:
        result['error_type'] = 'TimeoutError'
        result['error_hint'] = 'timeout'
except ValueError as exc:
    result['error_type'] = str(exc)
except Exception as exc:
    result['error_type'] = type(exc).__name__
finally:
    result['latency_seconds'] = round(time.monotonic() - start, 3)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Outcome:', result['outcome'], 'HTTP:', result.get('http_status', 'n/a'), 'Hint:', result.get('error_hint', result.get('error_type', '')), 'Evidence:', OUT)
