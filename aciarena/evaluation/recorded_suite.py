"""Manifest-selected Sequential evaluation; legacy suites remain available."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from pathlib import Path
import json

from .recorded_executor import RecordedTaskExecutor, ROOT
from .audit import audit_matrix, build_matrix_plan
from .records import canonical_hash
from .configuration import (
    ConfigurationError,
    experiment_manifest_directory,
    load_experiment_configuration,
)
from aciarena.attacks.catalog import AttackCatalog
from .task import MathTask, CodeTask


class RecordedEvaluationSuite:
    def __init__(self, args, *, model_config=None, judge_config=None,
                 utility_verifier=None, utility_verifier_version=None):
        self.args = copy.deepcopy(args)
        if (model_config is None) != (judge_config is None):
            raise ConfigurationError('Inject model and Judge configurations together')
        if model_config is None:
            if getattr(args, 'model_config', None) or getattr(args, 'judge_config', None):
                raise ConfigurationError('CrewAI reads model and Judge references from --experiment_config')
            config_path = getattr(args, 'experiment_config', 'configs/experiments/core.yaml')
            contract, model_config, judge_config = load_experiment_configuration(config_path)
            manifest_directory = experiment_manifest_directory(config_path, contract)
            catalog = AttackCatalog(manifest_directory / 'attacks.json')
            task_manifest_path = manifest_directory / 'tasks.json'
        else:
            contract = {'contract_id': 'injected-test-only'}
            catalog = None
            task_manifest_path = None
        if self.args.mas not in contract.get('active_mas', [self.args.mas]):
            raise ConfigurationError('Selected MAS is absent from the experiment contract')
        if self.args.task_domain not in contract.get('task_domains', [self.args.task_domain]):
            raise ConfigurationError('Selected domain is absent from the experiment contract')
        if not getattr(self.args, 'experiment_id', None):
            self.args.experiment_id = contract.get('default_experiment_id', 'crewai-development-v1')
        self.model_config = model_config
        self.executor = RecordedTaskExecutor(self.args, judge_config,
                                             catalog=catalog,
                                             task_manifest_path=task_manifest_path,
                                             utility_verifier=utility_verifier,
                                             utility_verifier_version=utility_verifier_version,
                                             experiment_contract=contract)
        if self.args.max_workers < 1:
            raise ValueError('max_workers must be positive')
        limit = getattr(self.args, 'limit', None)
        if limit is not None and limit < 1:
            raise ValueError('limit must be positive')
        tasks_by_id = {}
        for task_id, entry in self.executor.tasks.items():
            if entry['task_domain'] != self.args.task_domain:
                continue
            row = json.loads((ROOT / entry['source']).read_text())[entry['source_index']]
            cls = MathTask if self.args.task_domain == 'math' else CodeTask
            task = cls(query=row['problem'], ground_truth=row['answer'])
            task.task_id = task_id
            tasks_by_id[task_id] = task
        requested_task_ids = getattr(self.args, 'task_ids', None)
        if requested_task_ids:
            if limit is not None:
                raise ValueError('--task_ids and --limit cannot be combined')
            if len(set(requested_task_ids)) != len(requested_task_ids):
                raise ValueError('--task_ids must be unique')
            unknown = [task_id for task_id in requested_task_ids if task_id not in tasks_by_id]
            if unknown:
                raise ValueError(
                    f'Tasks are absent from the selected domain: {", ".join(unknown)}')
            self.tasks = [tasks_by_id[task_id] for task_id in requested_task_ids]
        else:
            self.tasks = list(tasks_by_id.values())
        if limit is not None:
            self.tasks = self.tasks[:limit]
        selections = [(task.task_id, attack_id) for task in self.tasks
                      for attack_id in self.executor.attack_ids]
        _, run_config = self.executor._configuration(self.model_config)
        self.plan = build_matrix_plan(
            experiment_id=self.executor.experiment_id,
            selections=selections,
            tasks=self.executor.tasks,
            catalog=self.executor.catalog,
            mas_id=self.args.mas,
            repetition=getattr(self.args, 'repetition', 1),
            phase=getattr(self.args, 'phase', 'pilot'),
            config_hash=canonical_hash(run_config),
        )

    def eval(self):
        rows = []
        with ThreadPoolExecutor(max_workers=self.args.max_workers) as pool:
            futures = [pool.submit(self.executor.execute, {'llm_config': self.model_config}, task,
                                   attack_id=attack_id, phase=getattr(self.args, 'phase', 'pilot'),
                                   repetition=getattr(self.args, 'repetition', 1),
                                   resume=getattr(self.args, 'resume', False),
                                   retry=getattr(self.args, 'retry_errors', False))
                       for task in self.tasks for attack_id in self.executor.attack_ids]
            try:
                for future in as_completed(futures):
                    rows.append(future.result())
            except BaseException:
                self.executor.stop.set()
                for future in futures:
                    future.cancel()
                raise
        report = audit_matrix(
            self.executor.writer,
            self.plan,
            self.executor.tasks,
            self.executor.catalog,
            allow_additional=True,
            require_injection=self.args.suite != 'benign',
        )
        if not report['ok']:
            raise RuntimeError(f'Experiment audit failed: {report["errors"]}')
        utility = [r for r in rows if r.status == 'success' and r.utility_status == 'valid']
        attacks = [r for r in rows if r.status == 'success' and r.attack_status == 'valid']
        result = {'experiment_id': self.executor.experiment_id, 'planned_runs': len(futures),
                  'returned_runs': len(rows), 'completed_runs': sum(r.is_complete for r in rows),
                  'execution_errors': sum(r.status != 'success' for r in rows),
                  'utility_denominator': len(utility), 'attack_denominator': len(attacks),
                  'utility_errors': sum(r.utility_status == 'error' for r in rows),
                  'utility_unknown': sum(r.utility_status == 'unknown' for r in rows),
                  'attack_errors': sum(r.attack_status == 'error' for r in rows),
                  'attack_unknown': sum(r.attack_status == 'unknown' for r in rows),
                  'attack_not_applicable': sum(
                      r.attack_id != 'none' and r.attack_status == 'not_applicable' for r in rows),
                  'target_not_invoked': sum(r.target_invoked is False for r in rows),
                  'payload_not_injected': sum(r.payload_injected is False for r in rows),
                  'records_dir': str(self.executor.writer.directory),
                  'audit': {key: value for key, value in report.items()
                            if key not in {'storage'}}}
        result['Benign Utility' if self.args.suite == 'benign' else 'Utility under Attack'] = (
            100 * sum(r.utility_success for r in utility) / len(utility) if utility else None)
        if self.args.suite != 'benign':
            result['Attack Success Rate'] = 100 * sum(r.attack_success for r in attacks) / len(attacks) if attacks else None
        return result
