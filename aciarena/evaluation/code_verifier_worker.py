"""Kernel-confined CodeTask verifier worker.

The parent launches this process in new user, network, and PID namespaces.
This worker additionally applies Landlock filesystem rules, resource limits,
and a seccomp deny-list before executing model-generated Python.
"""

import ctypes
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import resource
import signal
import sys


ROOT = Path(__file__).resolve().parents[2]


class SandboxUnavailable(RuntimeError):
    pass


def set_limits():
    mib = 1024 * 1024
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    resource.setrlimit(resource.RLIMIT_AS, (512 * mib, 512 * mib))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 * mib, 1 * mib))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def apply_landlock(workdir):
    libc = ctypes.CDLL(None, use_errno=True)
    create_ruleset, add_rule, restrict_self = 444, 445, 446  # Linux x86_64
    version = libc.syscall(create_ruleset, 0, 0, 1)
    if version < 1:
        raise SandboxUnavailable('Landlock is unavailable')

    # ABI 1 rights, plus rights introduced by ABI 2, 3, and 5.
    handled = (1 << 13) - 1
    if version >= 2:
        handled |= 1 << 13  # REFER
    if version >= 3:
        handled |= 1 << 14  # TRUNCATE
    if version >= 5:
        handled |= 1 << 15  # IOCTL_DEV

    class RulesetAttr(ctypes.Structure):
        _fields_ = [('handled_access_fs', ctypes.c_uint64)]

    class PathBeneathAttr(ctypes.Structure):
        _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int)]

    ruleset_attr = RulesetAttr(handled)
    ruleset_fd = libc.syscall(create_ruleset, ctypes.byref(ruleset_attr),
                              ctypes.sizeof(ruleset_attr), 0)
    if ruleset_fd < 0:
        raise SandboxUnavailable(f'Cannot create Landlock ruleset: errno {ctypes.get_errno()}')

    def allow(path, rights):
        path_fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        try:
            attr = PathBeneathAttr(rights, path_fd)
            if libc.syscall(add_rule, ruleset_fd, 1, ctypes.byref(attr), 0) != 0:
                raise SandboxUnavailable(f'Cannot add Landlock rule: errno {ctypes.get_errno()}')
        finally:
            os.close(path_fd)

    read_execute = (1 << 0) | (1 << 2) | (1 << 3)
    runtime_roots = {Path(sys.base_prefix), Path(sys.prefix), Path('/lib'), Path('/lib64')}
    for path in runtime_roots:
        if path.exists():
            allow(path, read_execute)
    allow(workdir, handled)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise SandboxUnavailable(f'Cannot enable no_new_privs: errno {ctypes.get_errno()}')
    if libc.syscall(restrict_self, ruleset_fd, 0) != 0:
        raise SandboxUnavailable(f'Cannot enforce Landlock: errno {ctypes.get_errno()}')
    os.close(ruleset_fd)


def apply_seccomp():
    libc = ctypes.CDLL(None, use_errno=True)

    class SockFilter(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte),
                    ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint32)]

    class SockFprog(ctypes.Structure):
        _fields_ = [('len', ctypes.c_ushort), ('filter', ctypes.POINTER(SockFilter))]

    # Network, process creation/escape, cross-process access, and host signalling.
    denied = [13, 14, 37, 38,
              41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
              56, 57, 58, 59, 62, 101, 200, 234, 272, 288, 308, 310, 311,
              322, 435, 438]
    filters = [
        SockFilter(0x20, 0, 0, 4),  # seccomp_data.arch
        SockFilter(0x15, 1, 0, 0xC000003E),  # AUDIT_ARCH_X86_64
        SockFilter(0x06, 0, 0, 0x80000000),  # kill unexpected architecture
        SockFilter(0x20, 0, 0, 0),  # seccomp_data.nr
        SockFilter(0x35, 0, 1, 0x40000000),  # reject the x32 syscall ABI
        SockFilter(0x06, 0, 0, 0x80000000),
    ]
    for number in denied:
        filters.extend((SockFilter(0x15, 0, 1, number),
                        SockFilter(0x06, 0, 0, 0x00050000 | errno.EPERM)))
    filters.append(SockFilter(0x06, 0, 0, 0x7FFF0000))  # SECCOMP_RET_ALLOW
    array = (SockFilter * len(filters))(*filters)
    program = SockFprog(len(filters), array)
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise SandboxUnavailable(f'Cannot enable no_new_privs: errno {ctypes.get_errno()}')
    if libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:
        raise SandboxUnavailable(f'Cannot enforce seccomp: errno {ctypes.get_errno()}')


def verify(request):
    from human_eval import execution

    workdir = Path(request['workdir']).resolve()
    if workdir.parent != Path('/tmp') or not workdir.name.startswith('aciarena-code-'):
        raise SandboxUnavailable('Invalid sandbox work directory')
    os.chdir(workdir)
    set_limits()
    apply_landlock(workdir)
    execution.reliability_guard()

    def timeout_handler(signum, frame):
        raise execution.TimeoutException('Timed out!')

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, 2.0)
    # Applied after installing the timer so generated code cannot replace,
    # block, or cancel the timeout signal.
    apply_seccomp()

    problem, code = request['ground_truth'], request['code']
    check_program = (problem.get('prompt', '') + code + '\n' + problem['test']
                     + '\n' + f"check({problem['entry_point']})")
    try:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            exec(check_program, {})
        return True
    except execution.TimeoutException:
        return False
    except BaseException:
        return False


def main():
    request = json.load(sys.stdin)
    value = verify(request)
    print(json.dumps({'value': value}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        print(json.dumps({'error_type': type(exc).__name__, 'error_message': str(exc)}))
        sys.exit(1)
