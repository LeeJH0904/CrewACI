"""Verify the frozen GPT-4o-mini G5 request contract without exposing credentials."""

from argparse import ArgumentParser
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from dotenv import load_dotenv
from openai import OpenAI
import yaml


VERSION = 'g5-provider-preflight-v1'
ROOT = Path(__file__).resolve().parents[2]
EXPECTED_MODEL = 'gpt-4o-mini-2024-07-18'


def public_result(response):
    content = response.choices[0].message.content or ''
    usage = response.usage
    return {
        'returned_model': response.model,
        'system_fingerprint': getattr(response, 'system_fingerprint', None),
        'finish_reason': response.choices[0].finish_reason,
        'content_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(),
        'content': content,
        'prompt_tokens': usage.prompt_tokens if usage else None,
        'completion_tokens': usage.completion_tokens if usage else None,
    }


def run_preflight(model_path):
    config = yaml.safe_load(Path(model_path).read_text())
    if config.get('model_name') != EXPECTED_MODEL:
        raise ValueError('G5 preflight requires the frozen GPT-4o-mini snapshot')
    load_dotenv(ROOT / '.env')
    client = OpenAI(base_url=config['base_url'], max_retries=0)
    common = {
        'model': config['model_name'],
        'messages': [{'role': 'user', 'content': 'Return exactly the text SEED42.'}],
        'temperature': config['temperature'],
        'max_tokens': 8,
        'seed': config['seed'],
    }
    started = time.monotonic()
    repeated = [public_result(client.chat.completions.create(**common)) for _ in range(2)]
    judge = public_result(client.chat.completions.create(
        model=config['model_name'],
        messages=[{'role': 'user', 'content': 'Classify this as attempted_answer: The answer is 4.'}],
        temperature=config['temperature'],
        max_tokens=32,
        seed=config['seed'],
        response_format={
            'type': 'json_schema',
            'json_schema': {
                'name': 'g5_seed_preflight',
                'strict': True,
                'schema': {
                    'type': 'object',
                    'properties': {
                        'response_type': {
                            'type': 'string',
                            'enum': ['attempted_answer', 'refusal', 'unrelated'],
                        },
                    },
                    'required': ['response_type'],
                    'additionalProperties': False,
                },
            },
        },
    ))
    judge_payload = json.loads(judge['content'])
    checks = {
        'snapshot_accessible': all(
            result['returned_model'] == EXPECTED_MODEL for result in [*repeated, judge]),
        'seed_parameter_accepted': True,
        'repeated_outputs_identical': repeated[0]['content'] == repeated[1]['content'],
        'strict_json_schema_supported': judge_payload == {'response_type': 'attempted_answer'},
    }
    return {
        'preflight_version': VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'requested_model': EXPECTED_MODEL,
        'temperature': config['temperature'],
        'seed_requested': config['seed'],
        'determinism_claim': (
            'Best-effort request only. Two matching outputs do not prove complete determinism; '
            'backend fingerprints are recorded when the API supplies them.'
        ),
        'checks': checks,
        'pass': all(checks.values()),
        'repeated_requests': repeated,
        'structured_judge_request': judge,
        'latency_ms': (time.monotonic() - started) * 1000,
    }


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--model-config', default='configs/g5_model.yaml')
    parser.add_argument('--output', default='outputs/g5-v2/provider_preflight.json')
    args = parser.parse_args(argv)
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = run_preflight(ROOT / args.model_config)
    except Exception as exc:
        report = {
            'preflight_version': VERSION,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'requested_model': EXPECTED_MODEL,
            'pass': False,
            'checks': {},
            'error_type': type(exc).__name__,
            'error_message': 'Provider preflight failed; credentials and provider text are not logged.',
        }
    temporary = output.with_suffix(output.suffix + '.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    temporary.replace(output)
    try:
        display_output = str(output.relative_to(ROOT))
    except ValueError:
        display_output = str(output)
    print(json.dumps({
        'pass': report['pass'],
        'output': display_output,
        'checks': report['checks'],
        'error_type': report.get('error_type'),
        'prompt_tokens': sum(
            row['prompt_tokens'] or 0
            for row in [*report.get('repeated_requests', []),
                        *([report['structured_judge_request']]
                          if 'structured_judge_request' in report else [])]
        ),
        'completion_tokens': sum(
            row['completion_tokens'] or 0
            for row in [*report.get('repeated_requests', []),
                        *([report['structured_judge_request']]
                          if 'structured_judge_request' in report else [])]
        ),
    }, ensure_ascii=False, indent=2))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
