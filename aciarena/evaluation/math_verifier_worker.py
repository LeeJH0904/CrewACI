"""Main-thread worker for pinned math verifier methods; no MAS/LLM imports.

Only trusted local method ASTs are compiled, never the model response. This
avoids importing the entire model stack in each short-lived verifier process.
"""

import ast
import hashlib
import json
import logging
from pathlib import Path
import resource
import sys
from types import MethodType, SimpleNamespace


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    request = json.load(sys.stdin)
    from math_verify import parse, verify, ExprExtractionConfig, LatexExtractionConfig
    from sympy.core.numbers import Integer

    permitted = {
        'utility': ('aciarena/evaluation/task/math_task.py', 'MathTask'),
        'mapping_agent': ('aciarena/attacks/hijacking_attack.py', 'AnswerMappingAgent'),
        'mapping_instruction': ('aciarena/attacks/hijacking_attack.py', 'AnswerMappingInsruction'),
    }
    path, class_name = permitted[request['kind']]
    raw = (Path(__file__).resolve().parents[2] / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != request['source_hash']:
        raise ValueError('Verifier source changed before worker execution')
    cls = next(node for node in ast.parse(raw).body if isinstance(node, ast.ClassDef) and node.name == class_name)
    namespace = dict(parse=parse, verify=verify, ExprExtractionConfig=ExprExtractionConfig,
                     LatexExtractionConfig=LatexExtractionConfig, Integer=Integer)
    obj = SimpleNamespace(ground_truth=request['ground_truth'], answer={
        'response': request['response'], 'ground_truth': request['ground_truth']})
    for method in cls.body:
        if isinstance(method, ast.FunctionDef) and method.name in ('extract_answer', 'apply_mapping', 'verify'):
            method_namespace = dict(namespace)
            exec(compile(ast.Module(body=[method], type_ignores=[]), path, 'exec'), method_namespace)
            function = method_namespace.pop(method.name)
            # Keep the imported comparison function in verify()'s globals.
            method_namespace.update(namespace)
            setattr(obj, method.name, MethodType(function, obj))
    errors = []

    class CaptureErrors(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                errors.append(record.getMessage())

    logging.getLogger().addHandler(CaptureErrors())
    gold, answer = obj.extract_answer(request['ground_truth'], request['response'])
    value = obj.verify() if gold and answer else None
    if errors:
        raise ValueError('Math verifier reported an internal comparison error')
    print(json.dumps({'value': value}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error_type': type(exc).__name__, 'error_message': str(exc)}))
        sys.exit(1)
