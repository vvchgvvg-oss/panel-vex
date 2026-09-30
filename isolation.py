#!/usr/bin/env python3
"""طبقة عزل تشغيل ملفات المستخدمين.

Docker هو الوضع الآمن للتشغيل. عند غيابه، لا يتم تشغيل أي امتداد غير
Python ولا تُنفّذ أوامر shell على مضيف اللوحة؛ وهذا يمنع Railway من تنفيذ
كود المستخدم مباشرة على حاوية اللوحة.
"""
import hashlib
import os
import re
import shlex
import subprocess
import sys

ISO_MEMORY = os.environ.get('ISO_MEMORY', '512m')
ISO_CPUS = os.environ.get('ISO_CPUS', '0.5')
ISO_PIDS = os.environ.get('ISO_PIDS', '128')
ISO_TMPFS_SIZE = os.environ.get('ISO_TMPFS_SIZE', '64m')
ISO_NETWORK = os.environ.get('ISO_NETWORK', 'none').lower()
ISO_FORCE_MODE = os.environ.get('ISO_MODE', 'auto').lower()
IMAGES = {
    'py': os.environ.get('ISO_IMAGE_PY', 'python:3.11-slim'),
    'js': os.environ.get('ISO_IMAGE_NODE', 'node:20-alpine'),
    'mjs': os.environ.get('ISO_IMAGE_NODE', 'node:20-alpine'),
    'cjs': os.environ.get('ISO_IMAGE_NODE', 'node:20-alpine'),
    'ts': os.environ.get('ISO_IMAGE_NODE', 'node:20-alpine'),
    'sh': os.environ.get('ISO_IMAGE_SH', 'alpine:3.19'),
    'php': os.environ.get('ISO_IMAGE_PHP', 'php:8.2-cli-alpine'),
    'rb': os.environ.get('ISO_IMAGE_RB', 'ruby:3.2-alpine'),
}
CONTAINER_HOME = '/home/container'
_docker_cache = None


def docker_available() -> bool:
    global _docker_cache
    if ISO_FORCE_MODE == 'sandbox':
        return False
    if _docker_cache is not None:
        return _docker_cache
    try:
        result = subprocess.run(
            ['docker', 'info', '--format', '{{.ServerVersion}}'],
            capture_output=True, text=True, timeout=8,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin'},
        )
        _docker_cache = result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        _docker_cache = False
    return _docker_cache


def isolation_mode() -> str:
    if ISO_FORCE_MODE == 'docker':
        return 'docker' if docker_available() else 'unavailable'
    return 'docker' if docker_available() else 'sandbox'


def _safe_name(username: str, filepath: str) -> str:
    digest = hashlib.sha256(f'{username}|{os.path.realpath(filepath)}'.encode()).hexdigest()[:12]
    base = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(username))[:24] or 'user'
    return f'panel_{base}_{digest}'


def is_inside(child: str, parent: str) -> bool:
    try:
        child_real = os.path.realpath(child)
        parent_real = os.path.realpath(parent).rstrip(os.sep) or os.sep
        return child_real == parent_real or child_real.startswith(parent_real + os.sep)
    except Exception:
        return False


def _image_for(ext: str) -> str:
    return IMAGES.get(ext, IMAGES['py'])


def _inner_command(ext: str, filename: str, has_requirements: bool,
                   has_package_json: bool) -> str:
    quoted = shlex.quote(filename)
    if ext == 'py':
        prefix = ''
        if has_requirements:
            prefix = ('pip install --no-cache-dir --user -q -r requirements.txt 2>&1; '
                      'echo "[*] Dependencies ready."; ')
        return f'{prefix}exec python -u {quoted}'
    if ext in ('js', 'mjs', 'cjs', 'ts'):
        prefix = ''
        if has_package_json:
            prefix = ('npm install --no-audit --no-fund --loglevel=error 2>&1; '
                      'echo "[*] Dependencies ready."; ')
        runner = 'npx -y tsx' if ext == 'ts' else 'node'
        return f'{prefix}exec {runner} {quoted}'
    if ext == 'sh':
        return f'exec sh {quoted}'
    if ext == 'php':
        return f'exec php {quoted}'
    if ext == 'rb':
        return f'exec ruby {quoted}'
    return f'exec python -u {quoted}'


def _docker_security_args() -> list[str]:
    uid = getattr(os, 'getuid', lambda: 1000)()
    gid = getattr(os, 'getgid', lambda: 1000)()
    network = ISO_NETWORK if ISO_NETWORK in {'none', 'bridge'} else 'none'
    return [
        '--user', f'{uid}:{gid}', '--read-only',
        '--tmpfs', f'/tmp:rw,noexec,nosuid,nodev,size={ISO_TMPFS_SIZE}',
        '--tmpfs', f'{CONTAINER_HOME}/.cache:rw,nosuid,nodev,size={ISO_TMPFS_SIZE}',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
        f'--memory={ISO_MEMORY}', f'--memory-swap={ISO_MEMORY}',
        f'--cpus={ISO_CPUS}', f'--pids-limit={ISO_PIDS}',
        '--ulimit', 'nofile=512:512', '--ulimit', 'nproc=128:128',
        '--network', network,
        '-e', 'HOME=/home/container', '-e', 'TMPDIR=/tmp',
        '-e', 'PYTHONUNBUFFERED=1', '-e', 'PYTHONDONTWRITEBYTECODE=1',
        '-e', 'PYTHONUSERBASE=/home/container/.cache/py',
        '-e', 'PATH=/home/container/.cache/py/bin:/usr/local/bin:/usr/bin:/bin',
        '-e', 'NPM_CONFIG_CACHE=/home/container/.cache/npm',
    ]


def build_docker_command(username: str, filepath: str) -> str:
    work_dir = os.path.dirname(os.path.realpath(filepath))
    filename = os.path.basename(filepath)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'py'
    name = _safe_name(username, filepath)
    has_req = os.path.isfile(os.path.join(work_dir, 'requirements.txt'))
    has_pkg = os.path.isfile(os.path.join(work_dir, 'package.json'))
    args = [
        'docker', 'rm', '-f', name, '>/dev/null', '2>&1', ';',
        'exec', 'docker', 'run', '--rm', '-i', '--name', name,
        '--hostname', 'container', '-v',
        shlex.quote(f'{work_dir}:{CONTAINER_HOME}:rw'), '-w', CONTAINER_HOME,
    ]
    args += _docker_security_args()
    args += [_image_for(ext), 'sh', '-c', shlex.quote(
        _inner_command(ext, filename, has_req, has_pkg))]
    return ' '.join(args)


def build_sandbox_command(filepath: str, sandbox_script: str):
    work_dir = os.path.dirname(os.path.realpath(filepath))
    filename = os.path.basename(filepath)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'py'
    if ext != 'py' or not os.path.isfile(sandbox_script):
        return None
    return ' '.join([
        shlex.quote(sys.executable), '-I', '-u', shlex.quote(sandbox_script),
        shlex.quote(work_dir), shlex.quote(filepath),
    ])


def clean_child_env() -> dict:
    keep = ('PATH', 'LANG', 'LC_ALL', 'TZ', 'TERM')
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update({
        'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', 'TMPDIR': '/tmp',
        'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
    })
    return env


def build_run_command(username: str, filepath: str, sandbox_script: str,
                      is_master: bool = False, fallback_cmd: str = None):
    if isolation_mode() == 'docker':
        return build_docker_command(username, filepath), 'docker'
    sandbox = build_sandbox_command(filepath, sandbox_script)
    if sandbox:
        return sandbox, 'sandbox'
    # Never run shell=True on the Railway host for a normal user.
    if is_master and fallback_cmd:
        return fallback_cmd, 'plain'
    return None, 'unavailable'


def stop_container(username: str, filepath: str) -> None:
    if not docker_available():
        return
    name = _safe_name(username, filepath)
    for args in (['docker', 'kill', name], ['docker', 'rm', '-f', name]):
        try:
            subprocess.run(args, capture_output=True, timeout=15,
                           env={'PATH': '/usr/local/bin:/usr/bin:/bin'})
        except Exception:
            pass


def build_shell_command(username: str, work_dir: str, command: str) -> str:
    work_dir = os.path.realpath(work_dir)
    args = [
        'docker', 'run', '--rm', '-i', '--hostname', 'container', '-v',
        shlex.quote(f'{work_dir}:{CONTAINER_HOME}:rw'), '-w', CONTAINER_HOME,
    ]
    args += _docker_security_args()
    args += [IMAGES['py'], 'sh', '-c', shlex.quote(command)]
    return ' '.join(args)


_ESCAPE_TOKENS = (
    '..', '/etc', '/root', '/proc', '/sys', '/dev', '/run', '/var', '/usr/lib',
    '/app', '/home', '/opt', '/boot', '/srv', '/media', '/mnt', '~/', 'sudo',
    'su ', 'doas', 'chroot', 'mount', 'nsenter', 'docker', 'kubectl',
    'systemctl', 'crontab', 'pkexec', 'setcap', 'docker.sock', '/passwd', '/shadow',
)


def command_escapes_jail(command: str, allowed_dir: str) -> bool:
    low = f' {command.lower()} '
    if any(token in low for token in _ESCAPE_TOKENS):
        return True
    try:
        pieces = shlex.split(command, comments=False, posix=True)
    except Exception:
        return True
    allowed_bins = ('/usr/bin/', '/bin/', '/usr/local/bin/', '/usr/sbin/')
    for piece in pieces:
        for word in re.split(r'[;&|`$()<>{}"\']+', piece):
            if word and word.startswith('/') and not (
                is_inside(word, allowed_dir) or word.startswith(allowed_bins)
            ):
                return True
    return False
