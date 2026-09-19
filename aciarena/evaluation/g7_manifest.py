"""Validated G7 system, target, task, and attack mappings."""

from collections import Counter
import hashlib
import json
from pathlib import Path

from aciarena.attacks.catalog import AttackCatalog

from .records import canonical_hash


ROOT = Path(__file__).resolve().parents[2]
G7_MANIFEST_DIRECTORY = ROOT / 'manifests/g7'


class G7ManifestError(ValueError):
    pass


def _load(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise G7ManifestError(f'Duplicate JSON key in {path}: {key}')
            result[key] = value
        return result

    return json.loads(Path(path).read_text(), object_pairs_hook=unique_object)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class G7Manifest:
    def __init__(self, directory=G7_MANIFEST_DIRECTORY):
        self.directory = Path(directory)
        self.system_document = _load(self.directory / 'systems.json')
        self.target_document = _load(self.directory / 'targets.json')
        self.identifier_document = _load(self.directory / 'identifiers.json')
        task_path = ROOT / self.identifier_document['task_mapping']['source_manifest']
        attack_path = ROOT / self.identifier_document['attack_mapping']['source_manifest']
        self.task_document = _load(task_path)
        self.attack_document = _load(attack_path)
        # This validates every pinned attack/dependency source without creating
        # a Judge or making a provider call.
        self.attack_catalog = AttackCatalog(attack_path)
        self.systems = {row['mas_id']: row for row in self.system_document['systems']}
        self.targets = self.target_document['targets']
        self.tasks = {row['task_id']: row for row in self.task_document['tasks']}
        self.attacks = {row['attack_id']: row for row in self.attack_document['attacks']}
        self.task_ids_by_hash = {}
        self.attack_ids_by_class = {}
        self._validate()

    def _validate(self):
        if self.system_document.get('manifest_version') != 'g7-systems-v1':
            raise G7ManifestError('Unsupported G7 systems manifest version')
        if self.target_document.get('manifest_version') != 'g7-targets-v1':
            raise G7ManifestError('Unsupported G7 targets manifest version')
        if self.identifier_document.get('manifest_version') != 'g7-identifiers-v1':
            raise G7ManifestError('Unsupported G7 identifier manifest version')
        expected_systems = {
            'crewai_seq_nodeleg', 'metagpt', 'autogen', 'camel', 'sc',
            'llm_debate', 'agentverse',
        }
        if (len(self.system_document['systems']) != len(self.systems)
                or set(self.systems) != expected_systems or 'mad' in self.systems):
            raise G7ManifestError('G7 must contain the paper six plus CrewAI, excluding MAD')
        if set(self.targets) != expected_systems:
            raise G7ManifestError('G7 target systems must exactly match system inventory')
        if len(self.task_document['tasks']) != len(self.tasks):
            raise G7ManifestError('Duplicate task ID in source task manifest')
        if self.systems['metagpt']['domains'] != ['code']:
            raise G7ManifestError('MetaGPT must be code-only')
        for mas_id, system in self.systems.items():
            expected_domains = ['code'] if mas_id == 'metagpt' else ['math', 'code']
            if system['domains'] != expected_domains:
                raise G7ManifestError(f'Domain policy mismatch for {mas_id}')
            if (system['agent_count'] != len(system['agents'])
                    or len(system['agents']) != len(set(system['agents']))):
                raise G7ManifestError(f'Agent count mismatch for {mas_id}')
            if system['response_agent'] not in system['agents']:
                raise G7ManifestError(f'Unknown response agent for {mas_id}')
            if system['topology'] not in {
                    'sequential', 'vertical', 'horizontal', 'hierarchical'}:
                raise G7ManifestError(f'Unknown topology for {mas_id}')
            if set(self.targets.get(mas_id, {})) != {
                    'hijacking', 'disruption', 'disclosure'}:
                raise G7ManifestError(f'Incomplete target mapping for {mas_id}')
            for goal, target in self.targets[mas_id].items():
                if target['local_agent'] not in system['agents']:
                    raise G7ManifestError(
                        f'Unknown local target {target["local_agent"]} for {mas_id}/{goal}')

        datasets = {}
        for dataset in self.task_document['datasets']:
            path = ROOT / dataset['source']
            if _sha256(path) != dataset['sha256']:
                raise G7ManifestError(f'Task dataset hash mismatch: {dataset["source"]}')
            rows = _load(path)
            if len(rows) != dataset['count']:
                raise G7ManifestError(f'Task dataset count mismatch: {dataset["source"]}')
            datasets[dataset['source']] = rows
        counts = Counter()
        for task_id, entry in self.tasks.items():
            rows = datasets[entry['source']]
            try:
                row = rows[entry['source_index']]
            except IndexError as exc:
                raise G7ManifestError(f'Invalid source index for {task_id}') from exc
            if (canonical_hash(row) != entry['task_hash']
                    or canonical_hash(row['answer']) != entry['ground_truth_hash']):
                raise G7ManifestError(f'Task content mapping mismatch for {task_id}')
            key = (entry['task_domain'], entry['task_hash'], entry['ground_truth_hash'])
            if key in self.task_ids_by_hash:
                raise G7ManifestError(f'Duplicate task content mapping for {task_id}')
            self.task_ids_by_hash[key] = task_id
            counts[entry['task_domain']] += 1
        if dict(counts) != self.identifier_document['task_mapping']['expected_counts']:
            raise G7ManifestError('G7 task mapping counts do not match the contract')

        declared = self.identifier_document['attack_mapping']['classes']
        if len(declared) != self.identifier_document['attack_mapping']['expected_unique_classes']:
            raise G7ManifestError('G7 attack mapping does not contain 22 classes')
        source_by_class = {row['class']: row for row in self.attack_document['attacks']}
        if set(self.attacks) != set(self.attack_catalog.specs):
            raise G7ManifestError('G7 and validated attack catalog inventories disagree')
        for mapping in declared:
            class_name = mapping['class']
            attack_id = mapping['attack_id']
            if class_name in self.attack_ids_by_class:
                raise G7ManifestError(f'Duplicate attack class mapping: {class_name}')
            if source_by_class.get(class_name, {}).get('attack_id') != attack_id:
                raise G7ManifestError(f'Attack class mapping mismatch: {class_name}')
            self.attack_ids_by_class[class_name] = attack_id
        if set(self.attack_ids_by_class) != set(source_by_class):
            raise G7ManifestError('G7 attack mapping is not an exact 22-class inventory')

    def resolve_task_id(self, task_domain, query, ground_truth):
        task_hash = canonical_hash({'problem': query, 'answer': ground_truth})
        ground_truth_hash = canonical_hash(ground_truth)
        try:
            return self.task_ids_by_hash[(task_domain, task_hash, ground_truth_hash)]
        except KeyError as exc:
            raise G7ManifestError('Legacy task content is absent from the frozen task mapping') from exc

    def resolve_attack_id(self, attack):
        class_name = f'{type(attack).__module__}.{type(attack).__name__}'
        try:
            return self.attack_ids_by_class[class_name]
        except KeyError as exc:
            raise G7ManifestError(f'Legacy attack class is not mapped: {class_name}') from exc

    def target(self, mas_id, task_domain, goal):
        try:
            system = self.systems[mas_id]
            target = self.targets[mas_id][goal]['local_agent']
        except KeyError as exc:
            raise G7ManifestError(f'Unsupported G7 system or goal: {mas_id}/{goal}') from exc
        if task_domain not in system['domains']:
            raise G7ManifestError(f'{mas_id} does not support {task_domain}')
        return target

    def attack_ids(self, task_domain, goal):
        return tuple(sorted(
            attack_id for attack_id, entry in self.attacks.items()
            if task_domain in entry['domains'] and entry['goal'] == goal
        ))

    def task_ids(self, task_domain):
        return tuple(
            entry['task_id'] for entry in sorted(
                (entry for entry in self.tasks.values()
                 if entry['task_domain'] == task_domain),
                key=lambda entry: (entry['source'], entry['source_index']),
            )
        )

    def dry_run_slice(self, mas_id, task_domain, goal):
        task_ids = self.task_ids(task_domain)
        attack_ids = self.attack_ids(task_domain, goal)
        target = self.target(mas_id, task_domain, goal)
        return {
            'mode': 'dry-run',
            'mas_id': mas_id,
            'task_domain': task_domain,
            'attack_goal': goal,
            'target_agent': target,
            'task_ids': list(task_ids),
            'attack_ids': list(attack_ids),
            'planned_logical_runs': len(task_ids) * len(attack_ids),
            'paid_api_calls_made': 0,
        }
