"""Project-local compatibility patch for ``human_eval.execution``."""

from typing import Dict, List

import human_eval.execution as _execution


def unsafe_execute(
    problem: Dict, completion: str, timeout: float, result: List
) -> None:
    """Run HumanEval code while restoring unlink for tempdir cleanup."""
    with _execution.create_tempdir():
        import os
        import shutil

        rmtree = shutil.rmtree
        rmdir = os.rmdir
        unlink = os.unlink
        chdir = os.chdir

        _execution.reliability_guard()

        check_program = (
            problem["prompt"]
            + completion
            + "\n"
            + problem["test"]
            + "\n"
            + f"check({problem['entry_point']})"
        )

        try:
            exec_globals = {}
            with _execution.swallow_io():
                with _execution.time_limit(timeout):
                    exec(check_program, exec_globals)
            result.append("passed")
        except _execution.TimeoutException:
            result.append("timed out")
        except BaseException as exc:
            result.append(f"failed: {exc}")
        finally:
            # TemporaryDirectory uses os.unlink internally during cleanup.
            shutil.rmtree = rmtree
            os.rmdir = rmdir
            os.unlink = unlink
            os.chdir = chdir


# check_correctness resolves unsafe_execute from the upstream module globals.
_execution.unsafe_execute = unsafe_execute
check_correctness = _execution.check_correctness

