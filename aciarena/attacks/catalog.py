"""Validated, immutable attack specifications and per-run object construction."""

import ast
import copy
import hashlib
import importlib
import inspect
import json
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base_attack import InstructionInjectionAttack, MaliciousAgentAttack, MessagePoisonAttack, NoneAttack


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / 'manifests/attacks.json'
HASH = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
TEXT = Annotated[str, Field(min_length=1)]
DOMAIN = Literal['math', 'code']
SURFACE_CLASSES = {'instruction': InstructionInjectionAttack, 'agent': MaliciousAgentAttack,
                   'message': MessagePoisonAttack}
# Semantic category/domain boundaries come from existing payload/verifier meaning.
# The manifest chooses a representative within these boundaries, not import order.
CATEGORIES = {
    'disclosure_generic_apikey': ('disclosure_attack', ('math', 'code'), ('ApikeyMessage',)),
    'disclosure_math_location': ('disclosure_attack', ('math',), ('MathLocationLeakAgent', 'MathLocationLeakInstruction')),
    'disclosure_math_name': ('disclosure_attack', ('math',), ('MathNameLeakAgent', 'MathNameLeakInstruction')),
    'disclosure_code_apikey': ('disclosure_attack', ('code',), ('CodeApikeyLeakAgent', 'CodeApikeyLeakInstruction', 'ApikeyMessage')),
    'disclosure_code_name': ('disclosure_attack', ('code',), ('CodeNameLeakAgent', 'CodeNameLeakInstruction')),
    'disruption_ddos': ('disruption_attack', ('math', 'code'), ('DDOSAgent', 'DDOSInstruction', 'DDOSMessage')),
    'disruption_misalign': ('disruption_attack', ('math', 'code'), ('MisalignAgent',)),
    'disruption_code_data_collection': ('disruption_attack', ('code',), ('CodeDisruptionAttack',)),
    'disruption_math_data_collection': ('disruption_attack', ('math',), ('MathDisruptionAttack',)),
    'hijacking_safety_check': ('hijacking_attack', ('code',), ('SafetyCheckAgent', 'SafetyCheckInstruction')),
    'hijacking_malicious_report': ('hijacking_attack', ('code',), ('MaliciousReportAgent', 'MaliciousReportInstruction')),
    'hijacking_answer_mapping': ('hijacking_attack', ('math',), ('AnswerMappingAgent', 'AnswerMappingInsruction')),
    'hijacking_math_invert': ('hijacking_attack', ('math',), ('MathInvertMessage',)),
}
G0_CATEGORIES = frozenset({
    'disclosure_math_location', 'disclosure_math_name', 'disclosure_code_apikey',
    'disclosure_code_name', 'disruption_ddos', 'hijacking_safety_check',
    'hijacking_malicious_report', 'hijacking_answer_mapping',
})
G5_CATEGORIES = frozenset(CATEGORIES)
DEPENDENCIES = frozenset({
    'aciarena/attacks/base_attack.py', 'aciarena/evaluation/task/math_task.py',
    'aciarena/evaluation/task/code_task.py', 'aciarena/evaluation/human_eval_execution.py',
})


class CatalogError(ValueError):
    """Manifest, source, or requested attack contract is invalid."""


class AttackSpec(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    attack_id: TEXT
    attack_category: TEXT
    class_path: TEXT = Field(alias='class')
    goal: Literal['disclosure', 'disruption', 'hijacking']
    surface: Literal['instruction', 'agent', 'message']
    domains: tuple[DOMAIN, ...]
    registered_domains: tuple[DOMAIN, ...]
    target: Literal['solver']
    source: TEXT
    source_sha256: HASH
    payload: TEXT
    payload_hash: HASH
    verifier: TEXT
    verifier_source_hash: HASH
    applicability: TEXT
    not_applicable_task_ids: tuple[TEXT, ...] = ()
    selection_reason: TEXT


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


class BenignAttack(NoneAttack):
    """A fresh no-op condition without a Judge or an attack-success verdict."""

    def __init__(self, args):
        self.args = copy.deepcopy(args)
        self.payload = None
        self.llm_judge = None
        self.answer = None
        self.malicious_agents = []
        self.turn_count = 0
        self.attack_id = 'none'
        self.spec = None

    def verify(self):
        return None


class AttackCatalog:
    def __init__(self, manifest_path=DEFAULT_MANIFEST):
        try:
            self.manifest_path = Path(manifest_path).resolve()
            raw = self.manifest_path.read_bytes()
            self.manifest_hash = hashlib.sha256(raw).hexdigest()
            manifest = json.loads(raw,
                                  object_pairs_hook=unique_json_object)
        except (OSError, ValueError) as exc:
            raise CatalogError('Cannot read a valid attack manifest') from exc
        manifest_version = manifest.get('manifest_version') if isinstance(manifest, dict) else None
        if manifest_version not in {'g0-v1', 'g5-v1', 'g5-v2'}:
            raise CatalogError('Unsupported attack manifest version')
        self.manifest_version = manifest_version
        entries = manifest.get('attacks')
        dependencies = manifest.get('dependencies')
        if not isinstance(entries, list) or not isinstance(dependencies, dict) or set(dependencies) != DEPENDENCIES:
            raise CatalogError('Manifest must contain attacks and the complete dependency fingerprints')
        self._dependencies = MappingProxyType(dict(dependencies))
        self._check_dependencies()
        specs, classes, categories, class_paths = {}, {}, set(), set()
        for entry in entries:
            try:
                # JSON-mode strict validation accepts arrays as immutable tuples.
                spec = AttackSpec.model_validate_json(json.dumps(entry))
            except ValueError as exc:
                raise CatalogError('Invalid attack specification') from exc
            if spec.attack_id in specs or spec.class_path in class_paths:
                raise CatalogError('Duplicate attack ID or class')
            classes[spec.attack_id] = self._validate_source(spec, manifest_version)
            specs[spec.attack_id] = spec
            categories.add(spec.attack_category)
            class_paths.add(spec.class_path)
        expected_categories = G0_CATEGORIES if manifest_version == 'g0-v1' else G5_CATEGORIES
        if categories != expected_categories:
            raise CatalogError('Attack categories do not match the manifest version policy')
        if manifest_version == 'g0-v1' and len(specs) != 8:
            raise CatalogError('G0 requires eight representative attacks')
        if manifest_version in {'g5-v1', 'g5-v2'} and len(specs) != 22:
            raise CatalogError('G5 requires all 22 unique Math/Code attacks')
        self._specs = MappingProxyType(specs)
        self._classes = MappingProxyType(classes)

    @property
    def specs(self):
        return self._specs

    def _check_dependencies(self):
        for source, expected in self._dependencies.items():
            actual = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
            if actual != expected:
                raise CatalogError(f'Dependency hash mismatch: {source}')

    def _validate_source(self, spec, manifest_version):
        policy = CATEGORIES.get(spec.attack_category)
        if policy is None:
            raise CatalogError('Unknown attack category')
        module_name, domains, names = policy
        module_path = f'aciarena.attacks.{module_name}'
        if spec.class_path not in {f'{module_path}.{name}' for name in names}:
            raise CatalogError('Class does not implement the selected category')
        if len(set(spec.domains)) != len(spec.domains) or set(spec.domains) != set(domains):
            raise CatalogError('Domain coverage disagrees with the category contract')
        if spec.goal != spec.attack_category.split('_', 1)[0]:
            raise CatalogError('Category and goal disagree')
        variant = ('v2' if manifest_version == 'g5-v2'
                   and spec.attack_category == 'hijacking_math_invert' else 'v1')
        if spec.attack_id != f'{spec.attack_category}.{spec.surface}.{variant}':
            raise CatalogError('Attack ID must identify the category, surface and variant version')
        if spec.source != f'aciarena/attacks/{module_name}.py':
            raise CatalogError('Class and source path disagree')
        raw = (ROOT / spec.source).read_bytes()
        if hashlib.sha256(raw).hexdigest() != spec.source_sha256:
            raise CatalogError(f'Source hash mismatch: {spec.source}')
        text = raw.decode('utf-8')
        tree = ast.parse(text)
        name = spec.class_path.rsplit('.', 1)[1]
        nodes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name]
        if len(nodes) != 1:
            raise CatalogError('Class must have exactly one source definition')
        node = nodes[0]
        registered = set()
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == 'register_attack_goal'):
                goal = ast.literal_eval(decorator.args[0])
                registered.update([goal.rsplit('_', 1)[1]] if goal.endswith(('_math', '_code')) else ['math', 'code'])
        if (set(spec.registered_domains) != registered or len(spec.registered_domains) != len(registered)
                or not set(spec.domains) <= registered):
            raise CatalogError('Manifest domains disagree with source registration')
        verifier = next(child for child in node.body if isinstance(child, ast.FunctionDef) and child.name == 'verify')
        if (spec.verifier != f'{spec.class_path}.verify'
                or sha256(ast.get_source_segment(text, verifier)) != spec.verifier_source_hash):
            raise CatalogError('Verifier identity or hash mismatch')
        module = importlib.import_module(module_path)
        cls = getattr(module, name)
        if cls.__module__ != module_path or Path(inspect.getfile(cls)).resolve() != (ROOT / spec.source).resolve():
            raise CatalogError('Imported class does not match the pinned source')
        if not issubclass(cls, SURFACE_CLASSES[spec.surface]):
            raise CatalogError('Class and attack surface disagree')
        # Resolve the existing literal payload without constructing a Judge.
        init = next(child for child in node.body if isinstance(child, ast.FunctionDef) and child.name == '__init__')
        assignments = [child for child in ast.walk(init) if isinstance(child, ast.Assign)
                       and any(isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                               and target.value.id == 'self' and target.attr == 'payload' for target in child.targets)]
        if len(assignments) != 1:
            raise CatalogError('Expected a single literal payload assignment')
        value = assignments[0].value
        payload = getattr(module, value.id) if isinstance(value, ast.Name) else ast.literal_eval(value)
        if payload != spec.payload or sha256(spec.payload) != spec.payload_hash:
            raise CatalogError('Payload content or hash mismatch')
        return cls

    def get(self, attack_id, *, task_domain, target='solver'):
        if task_domain not in ('math', 'code') or target != 'solver':
            raise CatalogError('Only Math/Code and the Solver target are supported')
        if attack_id == 'none':
            return None
        try:
            spec = self._specs[attack_id]
        except KeyError as exc:
            raise CatalogError(f'Unknown attack ID: {attack_id}') from exc
        if task_domain not in spec.domains:
            raise CatalogError(f'{attack_id} does not support {task_domain}')
        return spec

    def build(self, attack_id, *, task_domain, args, llm_config, target='solver'):
        if hashlib.sha256(self.manifest_path.read_bytes()).hexdigest() != self.manifest_hash:
            raise CatalogError('Attack manifest changed after catalog loading')
        spec = self.get(attack_id, task_domain=task_domain, target=target)
        if getattr(args, 'task_domain', task_domain) != task_domain:
            raise CatalogError('args.task_domain disagrees with the requested domain')
        if getattr(args, 'malicious_agents', None) not in (None, [], ['solver']):
            raise CatalogError('args.malicious_agents disagrees with the Solver target')
        self._check_dependencies()
        if spec is None:
            return BenignAttack(args)
        # Recheck even a reused catalog, before any provider initialization.
        cls = self._validate_source(spec, self.manifest_version)
        if cls is not self._classes[attack_id]:
            raise CatalogError('Attack class changed after catalog loading')
        attack = cls(args=copy.deepcopy(args), llm_config=copy.deepcopy(llm_config))
        if attack.payload != spec.payload:
            raise CatalogError('Constructed attack payload differs from its specification')
        attack.attack_id = attack_id
        attack.spec = spec
        return attack
