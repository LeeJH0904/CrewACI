"""Per-attempt observation of existing attack hooks; never applies an attack."""

import copy
from datetime import datetime, timezone
import json

from aciarena.evaluation.records import MessageRecord
from aciarena.evaluation.run_writer import StorageError


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class ProtocolError(ValueError):
    pass


class RunTrace:
    def __init__(self, writer, run_id, attempt_no, spec, stop, *, now=utc_now):
        self.writer, self.run_id, self.attempt_no = writer, run_id, attempt_no
        self.spec, self.stop = spec, stop
        self.now = now
        self.attack_id = spec.attack_id if spec else 'none'
        self.target_invoked = False if spec else None
        self.payload_injected = False if spec else None
        self.messages = []
        self.inputs = {}
        self.original_profiles = {}
        self.final_output = None
        self.call_count = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.usage_missing_calls = 0

    def emit(self, sender, receiver, phase, content, original=None, attacked=False):
        if self.stop.is_set():
            raise StorageError('Execution stopped after a storage failure')
        if not isinstance(content, str):
            raise ProtocolError('Agent messages must be strings')
        record = MessageRecord(run_id=self.run_id, attempt_no=self.attempt_no,
                               seq=len(self.messages) + 1, sender=sender, receiver=receiver,
                               phase=phase, content=content, original_content=original,
                               is_attacked=attacked, attack_id=self.attack_id, created_at=self.now())
        try:
            self.writer.append_message(record)
        except (StorageError, OSError) as exc:
            self.stop.set()
            raise StorageError('Message persistence failed; execution must stop') from exc
        self.messages.append(record)

    def log_message(self, sender, receiver, message, tool=None):
        phases = {('user', 'solver'): 'task', ('solver', 'reviewer'): 'context',
                  ('reviewer', 'finalizer'): 'review', ('finalizer', 'user'): 'final'}
        phase = phases.get((sender, receiver))
        if phase is None:
            raise ProtocolError('Unexpected Sequential message route')
        attacked = bool(self.spec and self.spec.surface == 'message' and sender == 'solver'
                        and receiver == 'reviewer' and message == self.spec.payload)
        self.emit(sender, receiver, phase, message, attacked=attacked)
        if attacked:
            self.payload_injected = True
        if phase == 'final':
            self.final_output = message

    def profiles(self, mas, originals):
        self.original_profiles = originals
        for name, agent in mas.agents.items():
            attacked = bool(self.spec and self.spec.surface == 'agent' and name == 'solver'
                            and agent.profile != originals[name] and self.spec.payload in agent.profile)
            self.emit(name, name, 'profile', agent.profile, originals[name], attacked)
            if attacked:
                self.payload_injected = True

    def attach_agent(self, name, agent):
        original = agent.run_step

        def run_step(query, *args, **kwargs):
            if self.stop.is_set():
                raise StorageError('Execution stopped after a storage failure')
            if self.spec and name == 'solver':
                self.target_invoked = True
            self.inputs[name] = query
            return original(query, *args, **kwargs)

        agent.run_step = run_step
        self.attach_llm(name, agent.llm)

    def _usage(self, prompt, completion):
        complete = True
        for field, value in [('prompt_tokens', prompt), ('completion_tokens', completion)]:
            if type(value) is int and value >= 0:
                setattr(self, field, getattr(self, field) + value)
            else:
                complete = False
        if not complete:
            self.usage_missing_calls += 1

    def attach_llm(self, name, llm, judge=False):
        from aciarena.agent_components.llms.openai_llm import OpenAILLM

        sdk_owner, sdk_method = None, None
        if isinstance(llm, OpenAILLM):
            sdk_owner, sdk_method = llm.client.chat.completions, 'create'
        if sdk_owner is not None:
            sdk_call = getattr(sdk_owner, sdk_method)

            def request(*args, **kwargs):
                self.call_count += 1
                try:
                    result = sdk_call(*args, **kwargs)
                except Exception:
                    self._usage(None, None)
                    raise
                usage = getattr(result, 'usage', None) or getattr(result, 'usage_metadata', None)
                self._usage(getattr(usage, 'prompt_tokens', getattr(usage, 'prompt_token_count', None)),
                            getattr(usage, 'completion_tokens', getattr(usage, 'candidates_token_count', None)))
                return result

            setattr(sdk_owner, sdk_method, request)
        original = llm.call_llm

        def call(messages, *args, **kwargs):
            snapshot = copy.deepcopy(messages)
            before = copy.deepcopy(snapshot)
            attacked = False
            if not judge and self.spec and name == 'solver':
                if self.spec.surface == 'instruction' and snapshot:
                    actual = snapshot[-1].get('content')
                    expected = self.inputs.get(name)
                    attacked = actual == f'{expected}\n{self.spec.payload}'
                    before[-1]['content'] = expected
                elif self.spec.surface == 'agent' and snapshot:
                    actual = snapshot[0].get('content', '')
                    attacked = actual != self.original_profiles[name] and self.spec.payload in actual
                    before[0]['content'] = self.original_profiles[name]
            phase = 'evaluation' if judge else 'llm_input'
            self.emit(name, 'llm', phase, json.dumps(snapshot, ensure_ascii=False),
                      json.dumps(before, ensure_ascii=False) if attacked else None, attacked)
            if attacked:
                self.payload_injected = True
            old_prompt = getattr(llm, 'input_tokens', None)
            old_completion = getattr(llm, 'output_tokens', None)
            if sdk_owner is None:
                self.call_count += 1
            try:
                result = original(messages, *args, **kwargs)
            except Exception:
                if sdk_owner is None:
                    self._usage(None, None)
                raise
            if sdk_owner is None:
                new_prompt, new_completion = getattr(llm, 'input_tokens', None), getattr(llm, 'output_tokens', None)
                self._usage(new_prompt - old_prompt if type(new_prompt) is int and type(old_prompt) is int else None,
                            new_completion - old_completion if type(new_completion) is int and type(old_completion) is int else None)
            if judge:
                self.emit('llm', name, 'evaluation', result)
            return result

        llm.call_llm = call
