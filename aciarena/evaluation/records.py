"""Versioned run/message contracts. Persistence is implemented separately."""

from datetime import datetime
import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


Nonempty = Annotated[str, Field(min_length=1)]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
PositiveInt = Annotated[int, Field(ge=1)]
NonnegativeInt = Annotated[int, Field(ge=0)]
Phase = Literal['calibration', 'pilot', 'core', 'confirmation']
Domain = Literal['math', 'code']
Surface = Literal['instruction', 'agent', 'message']
AttackCategory = Literal[
    'disclosure_math_location', 'disclosure_math_name', 'disclosure_code_apikey',
    'disclosure_code_name', 'disruption_ddos', 'hijacking_safety_check',
    'hijacking_malicious_report', 'hijacking_answer_mapping',
]
RETRYABLE_ERROR_TYPES = frozenset({
    'APITimeoutError', 'APIConnectionError', 'RateLimitError', 'TimeoutError'
})


def canonical_hash(value: JsonValue) -> str:
    """SHA-256 of UTF-8, sorted compact JSON; non-finite numbers are rejected."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True, allow_inf_nan=False)


class RunIdentity(Record):
    experiment_id: Nonempty
    task_id: Nonempty
    mas_id: Nonempty
    implementation: Literal['reconstructed', 'native']
    attack_id: Nonempty
    repetition: PositiveInt
    phase: Phase
    config_hash: Digest

    def deterministic_id(self) -> str:
        identity = {key: getattr(self, key) for key in RunIdentity.model_fields}
        return 'run_' + canonical_hash(identity)


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('Timestamp must include a timezone')
    return parsed


class RunRecord(RunIdentity):
    schema_version: Literal['1.0'] = '1.0'
    run_id: Nonempty
    attempt_no: PositiveInt
    task_domain: Domain
    topology: Literal['sequential']
    model: Nonempty
    temperature: Annotated[float, Field(ge=0)]
    max_tokens: PositiveInt
    seed: int | None
    prompt_version: Nonempty
    verifier_version: Nonempty
    attack_category: AttackCategory | None
    attack_goal: Literal['disclosure', 'disruption', 'hijacking'] | None
    attack_surface: Surface | None
    malicious_agent: Literal['solver'] | None
    payload_hash: Digest | None
    target_invoked: bool | None
    payload_injected: bool | None
    raw_response: str | None
    response: str | None
    response_agent: Literal['finalizer'] | None
    ground_truth: JsonValue
    utility_success: bool | None
    utility_status: Literal['valid', 'unknown', 'error']
    attack_success: bool | None
    attack_status: Literal['valid', 'unknown', 'error', 'not_applicable']
    status: Literal['success', 'model_error', 'timeout', 'protocol_error', 'budget_exhausted']
    error_type: Nonempty | None
    error_message: Nonempty | None
    # Evaluation failures are separate from execution failures.
    utility_error_type: Nonempty | None = None
    utility_error_message: Nonempty | None = None
    attack_error_type: Nonempty | None = None
    attack_error_message: Nonempty | None = None
    llm_call_count: NonnegativeInt | None
    prompt_tokens: NonnegativeInt | None
    completion_tokens: NonnegativeInt | None
    latency_ms: Annotated[float, Field(ge=0)] | None
    started_at: Nonempty
    finished_at: Nonempty

    @model_validator(mode='after')
    def check_contract(self):
        if self.run_id != self.deterministic_id():
            raise ValueError('run_id does not match logical run identity')
        if timestamp(self.finished_at) < timestamp(self.started_at):
            raise ValueError('finished_at precedes started_at')
        if self.status == 'success':
            if any(value is None for value in (self.raw_response, self.response, self.response_agent)):
                raise ValueError('Successful execution requires raw/normalized output and source')
            if self.error_type is not None or self.error_message is not None:
                raise ValueError('Successful execution cannot carry an execution error')
        elif self.error_type is None or self.error_message is None:
            raise ValueError('Execution failure requires error type and message')

        for kind in ('utility', 'attack'):
            state = getattr(self, f'{kind}_status')
            outcome = getattr(self, f'{kind}_success')
            if (state == 'valid') != (outcome is not None):
                raise ValueError(f'{kind}: only valid evaluations have a boolean outcome')
            error = (getattr(self, f'{kind}_error_type'), getattr(self, f'{kind}_error_message'))
            if state == 'error':
                if any(value is None for value in error):
                    raise ValueError(f'{kind}: evaluation error requires details')
            elif any(value is not None for value in error):
                raise ValueError(f'{kind}: error details require error status')

        attack_fields = (self.attack_category, self.attack_goal, self.attack_surface,
                         self.malicious_agent, self.payload_hash)
        if self.attack_id == 'none':
            if any(value is not None for value in (*attack_fields, self.target_invoked, self.payload_injected)):
                raise ValueError('Benign attack fields must be null')
            if self.attack_status != 'not_applicable':
                raise ValueError('Benign attack_status must be not_applicable')
        else:
            if any(value is None for value in attack_fields):
                raise ValueError('Attack runs require category/goal/surface/target/payload hash')
            if (self.attack_status == 'not_applicable'
                    and self.attack_category != 'hijacking_answer_mapping'):
                raise ValueError('Only AnswerMapping has task-level inapplicability')
            if self.attack_category.split('_', 1)[0] != self.attack_goal:
                raise ValueError('Attack category and goal disagree')
            if self.status == 'success' and (self.target_invoked is None or self.payload_injected is None):
                raise ValueError('Successful attack runs require observed activation flags')
        return self

    @property
    def is_complete(self) -> bool:
        """Valid false outcomes are complete; never retry to obtain a better answer."""
        expected_attack_states = {'not_applicable'} if self.attack_id == 'none' else {
            'valid', 'not_applicable'}
        return (self.status == 'success' and self.utility_status == 'valid'
                and self.attack_status in expected_attack_states)


class MessageRecord(Record):
    schema_version: Literal['1.0'] = '1.0'
    run_id: Annotated[str, Field(pattern=r'^run_[0-9a-f]{64}$')]
    attempt_no: PositiveInt
    seq: PositiveInt
    sender: Nonempty
    receiver: Nonempty
    phase: Literal['task', 'profile', 'llm_input', 'context', 'review', 'final', 'evaluation']
    content: str
    original_content: str | None
    is_attacked: bool
    attack_id: Nonempty
    created_at: Nonempty

    @model_validator(mode='after')
    def check_contract(self):
        timestamp(self.created_at)
        if self.is_attacked and self.attack_id == 'none':
            raise ValueError('Directly attacked messages require an attack ID')
        return self
