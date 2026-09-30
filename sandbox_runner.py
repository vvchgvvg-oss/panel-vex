#!/usr/bin/env python3
"""مشغل Python احتياطي عند غياب Docker.

هذا الوضع لا يدّعي عزل kernel؛ لذلك يقيّد الملفات والعمليات ويُستخدم فقط
لملفات Python. الوضع الموصى به للإنتاج هو Docker مع daemon منفصل.
"""
import builtins
import ipaddress
import os
import sys

if len(sys.argv) != 3:
    print('Usage: sandbox_runner.py <allowed_dir> <script_path>')
    raise SystemExit(2)

ALLOWED_DIR = os.path.realpath(sys.argv[1])
SCRIPT_PATH = os.path.realpath(sys.argv[2])


def inside(path, parent=ALLOWED_DIR):
    try:
        child = os.path.realpath(os.fsdecode(path))
        root = os.path.realpath(parent).rstrip(os.sep) or os.sep
        return child == root or child.startswith(root + os.sep)
    except Exception:
        return False

if not inside(SCRIPT_PATH):
    print('BLOCKED: script outside allowed directory')
    raise SystemExit(13)

_KEEP_ENV = {
    'PATH', 'LANG', 'LC_ALL', 'TZ', 'TERM', 'PYTHONUNBUFFERED',
    'PYTHONDONTWRITEBYTECODE', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
    'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'NIX_SSL_CERT_FILE',
}
for key in list(os.environ):
    if key not in _KEEP_ENV:
        os.environ.pop(key, None)
os.environ.update({'HOME': ALLOWED_DIR, 'TMPDIR': os.path.join(ALLOWED_DIR, '.tmp')})
os.makedirs(os.environ['TMPDIR'], exist_ok=True)
os.chdir(ALLOWED_DIR)

import site as _site  # noqa: E402
READONLY = {os.path.realpath(sys.prefix), os.path.realpath(sys.base_prefix),
            os.path.realpath(os.path.dirname(os.__file__))}
try:
    READONLY.update(os.path.realpath(p) for p in _site.getsitepackages())
except Exception:
    pass
READONLY.update(['/etc/ssl', '/etc/pki', '/etc/ca-certificates',
                 '/usr/share/ca-certificates', '/usr/lib/ssl'])
READONLY_FILES = {'/etc/hosts', '/etc/resolv.conf', '/etc/nsswitch.conf',
                  '/etc/services', '/etc/protocols', '/etc/host.conf',
                  '/etc/gai.conf', '/etc/localtime', '/etc/timezone'}
SAFE_DEVICES = {'/dev/null', '/dev/zero', '/dev/urandom', '/dev/random', '/dev/tty'}
WRITE_CHARS = set('wax+')


def allowed(path, write=False):
    try:
        if isinstance(path, int):
            return True
        value = os.fsdecode(path)
        if not os.path.isabs(value):
            value = os.path.join(os.getcwd(), value)
        resolved = os.path.realpath(value)
        if resolved in SAFE_DEVICES:
            return True
        if inside(resolved):
            return True
        if write:
            return False
        if resolved in READONLY_FILES:
            return True
        return any(inside(resolved, prefix) for prefix in READONLY)
    except Exception:
        return False


def deny(reason, detail=''):
    raise PermissionError(f'BLOCKED: {reason} {detail}')


BLOCKED_EVENTS = {
    'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn',
    'os.fork', 'os.forkpty', 'pty.spawn', 'os.startfile', 'os.chroot',
    'os.setuid', 'os.setgid', 'os.seteuid', 'os.setegid', 'os.chown',
    'os.putenv', 'os.unsetenv', 'ctypes.dlopen', 'ctypes.dlsym',
    'ctypes.call_function', 'sys.settrace', 'sys.setprofile',
}
READ_EVENTS = {'open', 'builtins.open', 'io.open', 'io.open_code', 'os.open',
               'os.listdir', 'os.scandir', 'os.stat', 'os.lstat', 'os.statvfs',
               'glob.glob', 'pathlib.Path.glob'}
WRITE_EVENTS = {'os.remove', 'os.unlink', 'os.rmdir', 'os.mkdir', 'os.makedirs',
                'os.rename', 'os.replace', 'os.link', 'os.symlink', 'os.truncate',
                'os.utime', 'shutil.copyfile', 'shutil.move', 'shutil.rmtree',
                'shutil.unpack_archive'}


def first_path(args):
    for arg in args or ():
        if isinstance(arg, (str, bytes)):
            return arg
    return None


def private_host(host):
    try:
        return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback \
            or ipaddress.ip_address(host).is_link_local or ipaddress.ip_address(host).is_reserved
    except ValueError:
        return str(host).lower() in {'localhost', 'ip6-localhost'}


def audit(event, args):
    if event in BLOCKED_EVENTS or event.startswith('ctypes.'):
        deny(event)
    if event in READ_EVENTS:
        path = first_path(args)
        if path is not None:
            mode = ''.join(str(x) for x in (args or ())[1:] if isinstance(x, str))
            if not allowed(path, any(c in WRITE_CHARS for c in mode)):
                deny('path', path)
    elif event in WRITE_EVENTS:
        for arg in args or ():
            if isinstance(arg, (str, bytes)) and not allowed(arg, True):
                deny('write outside user directory', arg)
    elif event in {'socket.connect', 'socket.bind'}:
        address = args[1] if len(args) > 1 else None
        if isinstance(address, (str, bytes)):
            deny('local socket', address)
        if isinstance(address, tuple) and address and isinstance(address[0], str) and private_host(address[0]):
            deny('private network', address[0])
    elif event == 'import':
        filename = args[1] if len(args) > 1 else None
        if isinstance(filename, str) and filename.endswith(('.so', '.pyd')) and not allowed(filename):
            deny('native extension', filename)


sys.addaudithook(audit)

try:
    import resource
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    resource.setrlimit(resource.RLIMIT_NOFILE, (512, 512))
    resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
except Exception:
    pass

_real_open = builtins.open

def guarded_open(file, mode='r', *args, **kwargs):
    if not isinstance(file, int) and not allowed(file, any(c in WRITE_CHARS for c in str(mode))):
        deny('open', file)
    return _real_open(file, mode, *args, **kwargs)

builtins.open = guarded_open
sys.path = [ALLOWED_DIR] + [p for p in sys.path if p not in ('', '.', ALLOWED_DIR)]
sys.argv = [SCRIPT_PATH]
_globals = {'__name__': '__main__', '__file__': SCRIPT_PATH, '__builtins__': builtins}
try:
    with _real_open(SCRIPT_PATH, 'rb') as stream:
        code = compile(stream.read(), SCRIPT_PATH, 'exec')
    exec(code, _globals)
except PermissionError as exc:
    print(str(exc), flush=True)
    raise SystemExit(13)
except SystemExit:
    raise
except Exception:
    import traceback
    traceback.print_exc()
    raise SystemExit(1)
