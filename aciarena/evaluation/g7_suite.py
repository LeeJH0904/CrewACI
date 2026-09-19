"""Deterministic per-invocation G7 legacy suite."""

import json

from .g7_audit import audit_g7, build_g7_plan
from .g7_manifest import G7Manifest, G7ManifestError
from .legacy_recording import LegacyRecordedExecutor, ROOT
from .records import canonical_hash
from .task import CodeTask, MathTask


class G7LegacyEvaluationSuite:
    def __init__(self, args, model_config, judge_config, *, writer=None,
                 mas_builder=None):
        self.args = args
        if args.max_workers != 1:
            raise ValueError('G7 legacy baseline requires --max_workers 1')
        self.manifest = G7Manifest()
        kwargs = {'writer': writer, 'manifest': self.manifest}
        if mas_builder is not None:
            kwargs['mas_builder'] = mas_builder
        self.executor = LegacyRecordedExecutor(
            args, model_config, judge_config, **kwargs)
        all_task_ids = list(self.manifest.task_ids(args.task_domain))
        requested = getattr(args, 'task_ids', None)
        limit = getattr(args, 'limit', None)
        if requested and limit is not None:
            raise ValueError('--task_ids and --limit cannot be combined')
        if requested:
            if len(requested) != len(set(requested)):
                raise ValueError('--task_ids must be unique')
            unknown = sorted(set(requested) - set(all_task_ids))
            if unknown:
                raise G7ManifestError(
                    'Tasks are absent from the selected domain: ' + ', '.join(unknown))
            task_ids = list(requested)
        else:
            if limit is not None and limit < 1:
                raise ValueError('--limit must be positive')
            task_ids = all_task_ids[:limit]
        self.task_ids = tuple(task_ids)
        requested_attacks = getattr(args, 'attack_ids', None)
        available = (('none',) if args.suite == 'benign'
                     else self.manifest.attack_ids(args.task_domain, args.suite))
        if requested_attacks:
            if args.suite == 'benign':
                raise ValueError('Benign G7 runs do not accept attack IDs')
            if len(requested_attacks) != len(set(requested_attacks)):
                raise ValueError('--attack_ids must be unique')
            unknown = sorted(set(requested_attacks) - set(available))
            if unknown:
                raise G7ManifestError(
                    'Attack IDs are outside the selected goal/domain: ' + ', '.join(unknown))
            available = tuple(requested_attacks)
        self.attack_ids = tuple(available)
        self.tasks = self._load_tasks()
        self.config_hash = canonical_hash(self.executor.configuration())
        self.plan = build_g7_plan(
            experiment_id=self.executor.experiment_id,
            mas_id=args.mas,
            task_ids=self.task_ids,
            attack_ids=self.attack_ids,
            repetition=getattr(args, 'repetition', 1),
            phase=getattr(args, 'phase', 'core'),
            config_hash=self.config_hash,
        )

    def _load_tasks(self):
        tasks = []
        for task_id in self.task_ids:
            entry = self.manifest.tasks[task_id]
            row = json.loads((ROOT / entry['source']).read_text())[entry['source_index']]
            cls = MathTask if entry['task_domain'] == 'math' else CodeTask
            task = cls(query=row['problem'], ground_truth=row['answer'])
            task.task_id = task_id
            tasks.append(task)
        return tasks

    def dry_run(self):
        target = None if self.args.suite == 'benign' else (
            self.args.malicious_agents[0] if self.args.malicious_agents
            else self.manifest.target(
                self.args.mas, self.args.task_domain, self.args.suite))
        return {
            'mode': 'dry-run',
            'paid_api_calls_made': 0,
            'experiment_id': self.executor.experiment_id,
            'config_hash': self.config_hash,
            'mas_id': self.args.mas,
            'task_domain': self.args.task_domain,
            'suite': self.args.suite,
            'target_agent': target,
            'task_ids': list(self.task_ids),
            'attack_ids': list(self.attack_ids),
            'logical_runs': len(self.plan.expected),
            'records_dir': str(self.executor.writer.directory)
                if hasattr(self.executor.writer, 'directory') else None,
        }

    def eval(self):
        rows = []
        for task in self.tasks:
            for attack_id in self.attack_ids:
                rows.append(self.executor.execute(
                    task,
                    task_id=task.task_id,
                    attack_id=attack_id,
                    repetition=getattr(self.args, 'repetition', 1),
                    phase=getattr(self.args, 'phase', 'core'),
                    resume=getattr(self.args, 'resume', False),
                    retry=getattr(self.args, 'retry_errors', False),
                ))
        audit = audit_g7(
            self.executor.writer,
            self.plan,
            self.manifest,
            allow_additional=True,
            # D54 keeps non-invoked/non-injected rows as headline failures (zero)
            # instead of making a whole per-invocation slice fail its audit.
            require_injection=False,
        )
        if not audit['ok']:
            raise RuntimeError(f'G7 experiment audit failed: {audit["errors"]}')
        utility = [row for row in rows
                   if row.status == 'success' and row.utility_status == 'valid']
        attacks = [row for row in rows
                   if row.status == 'success' and row.attack_status == 'valid']
        result = {
            'mode': 'execute',
            'experiment_id': self.executor.experiment_id,
            'config_hash': self.config_hash,
            'planned_runs': len(self.plan.expected),
            'returned_runs': len(rows),
            'completed_runs': sum(row.is_complete for row in rows),
            'execution_errors': sum(row.status != 'success' for row in rows),
            'utility_denominator': len(utility),
            'attack_denominator': len(attacks),
            'utility_errors': sum(row.utility_status == 'error' for row in rows),
            'attack_errors': sum(row.attack_status == 'error' for row in rows),
            'usage_missing_calls': sum(row.usage_missing_calls for row in rows),
            'records_dir': str(self.executor.writer.directory),
            'audit': {key: value for key, value in audit.items() if key != 'storage'},
        }
        label = 'Benign Utility' if self.args.suite == 'benign' else 'Utility under Attack'
        result[label] = (
            100 * sum(row.utility_success for row in utility) / len(utility)
            if utility else None
        )
        if self.args.suite != 'benign':
            result['Attack Success Rate'] = (
                100 * sum(row.attack_success for row in attacks) / len(attacks)
                if attacks else None
            )
        return result
