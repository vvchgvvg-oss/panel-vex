# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  🔥 VEX  VPS - VPS Control Panel                                           ║
║  # 𝚅𝙿𝚂 𝙾𝙼𝙰𝚁                                                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║  - لوحة تحكم ويب (Flask) لإدارة VPS كاملة                                 ║
║  - تصميم مطابق لـ Lunes Host LLC (Pterodactyl style)                      ║
║  - متوافق مع Replit (يدعم بورتات متعددة)                                  ║
║  - تشغيل: python vps_panel.py                                             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import gc
import re
import ast
import json
import time
import uuid
import html
import shutil
import socket
import signal
import string
import random
import secrets
import hashlib
import logging
import platform
import zipfile
import tarfile
import threading
import subprocess
try:
    import isolation
except Exception:
    isolation = None
import warnings
from datetime import datetime, timedelta
from functools import wraps
from collections import deque

try:
    import resource
except ImportError:
    resource = None

try:
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, send_file, send_from_directory

warnings.filterwarnings('ignore')

# =============================================================================
# 0)  🔒 SECURITY — إغلاق الثغرات وحماية الموقع
# =============================================================================
# 🔒 امتدادات ثنائية خطيرة فقط — Python/JS/etc مسموح بها للرفع والتشغيل
BLOCKED_EXTENSIONS = {
    '.exe', '.dll', '.so', '.bin', '.elf',   # ملفات تنفيذية ثنائية
    '.php', '.php3', '.php4', '.php5', '.phtml',  # web shells
    '.htaccess', '.htpasswd',                 # إعدادات Apache
}

# 🔒 أوامر محظورة على المستخدمين العاديين في الـ terminal
BLOCKED_COMMANDS = [
    # تدمير النظام
    'rm -rf /', 'rm -rf ~', 'rm -fr /', 'mkfs', 'dd if=/dev',
    ':(){:|:&};:', 'fork bomb',
    # صلاحيات وجذر
    'chmod 777 /', 'chmod -R 777', 'chown root', 'chown -R',
    'sudo su', 'sudo -s', 'sudo -i', 'sudo bash', 'sudo sh',
    'passwd root', 'passwd ', 'su root', 'su -',
    # شبكة خطيرة
    'nc -e', 'nc -l', 'ncat', 'netcat',
    '>/dev/tcp', '>/dev/udp', '<&/dev/tcp', '<&/dev/udp',
    'curl | sh', 'curl|sh', 'wget | sh', 'wget|sh',
    'curl | bash', 'wget | bash',
    # ملفات النظام الحساسة
    '/etc/shadow', '/etc/sudoers', '/etc/passwd',
    '/etc/ssh/', 'id_rsa', 'authorized_keys',
    '/proc/sysrq', '/proc/sys/',
    # جدار الحماية والشبكة
    'iptables', 'ufw ', 'nftables',
    'ifconfig', 'ip route', 'route add',
    # تنفيذ كود خارجي
    'python -c "import os;os.system', "python -c 'import os;os.system",
    'exec(', 'eval(', '__import__(',
    # محاكاة نظام / هروب من Sandbox
    'chroot', 'unshare', 'nsenter', 'mount ',
    'docker ', 'kubectl', 'systemctl', 'service ',
    'crontab', 'at ', 'batch',
    # تسريب بيانات
    'base64 -d', 'openssl enc', 'gpg --decrypt',
    '../', '/etc/', '/root/', '/home/',
]

def secure_filename_safe(filename):
    """تنظيف اسم الملف ومنع path traversal"""
    from werkzeug.utils import secure_filename as wz_secure
    filename = wz_secure(filename)
    if not filename:
        filename = 'upload_' + str(int(time.time()))
    return filename

def is_extension_blocked(filename):
    """التحقق من امتداد الملف — فقط الملفات الثنائية الخطيرة"""
    ext = os.path.splitext(filename.lower())[1]
    return ext in BLOCKED_EXTENSIONS

def is_command_blocked(cmd, username):
    """فحص الأوامر الخطيرة — المالك مسموح له بكل شيء"""
    if username == MASTER_USERNAME:
        return False, None
    cmd_lower = cmd.lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in cmd_lower:
            return True, blocked
    return False, None

# =============================================================================
# 1)  وضع المصادر اللا‌محدود
# =============================================================================
def set_unlimited_resources():
    """لا تُلغى حدود عملية اللوحة؛ حدود ملفات المستخدمين تُطبق داخل العزل."""
    return False
UNLIMITED_ACTIVE = False
# =============================================================================
# 2)  المسارات والإعدادات (Replit-friendly)
# =============================================================================
# على Replit، استخدم المجلد الحالي بدل /tmp
DEFAULT_BASE = os.environ.get('BASE_PATH') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'panel_data')
BASE_PATH          = DEFAULT_BASE
os.makedirs(BASE_PATH, exist_ok=True)

USERS_FOLDER       = os.path.join(BASE_PATH, 'users_data')
USERS_FILE         = os.path.join(BASE_PATH, 'users.json')
PROCESSES_FILE     = os.path.join(BASE_PATH, 'processes.json')
SCHEDULES_FILE     = os.path.join(BASE_PATH, 'schedules.json')
LOGS_FILE          = os.path.join(BASE_PATH, 'activity.log')
USER_SESSIONS_FILE = os.path.join(BASE_PATH, 'user_sessions.json')
BACKUPS_FOLDER     = os.path.join(BASE_PATH, 'backups')
TEMP_FOLDER        = os.path.join(BASE_PATH, 'temp')
PACKAGES_FILE      = os.path.join(BASE_PATH, 'packages.json')
DOCKER_FILE        = os.path.join(BASE_PATH, 'docker.json')
MASTER_CONFIG_FILE = os.path.join(BASE_PATH, 'master_config.json')
BOT_CONFIG_FILE    = os.path.join(BASE_PATH, 'bot_config.json')
BOT_DATA_FILE      = os.path.join(BASE_PATH, 'bot_data.json')
PORTS_FILE         = os.path.join(BASE_PATH, 'ports.json')
ACTIVITY_FILE      = os.path.join(BASE_PATH, 'activity_feed.json')

PROFILE_IMAGE_URL = "https://g.top4top.io/s_3781e6bx47.jpg"
ENTRY_SOUND_URL   = "https://b.top4top.io/m_3779fnnpd1.m4a"

# ملفات إعدادات المالك الخاصة
OWNER_CONFIG_FILE  = os.path.join(BASE_PATH, 'owner_config.json')
MAINTENANCE_FILE   = os.path.join(BASE_PATH, 'maintenance.json')
BOT_STATS_FILE     = os.path.join(BASE_PATH, 'bot_stats.json')
ANNOUNCE_FILE      = os.path.join(BASE_PATH, 'announcements.json')
IPS_FILE           = os.path.join(BASE_PATH, 'ips_pool.json')

# =============================================================================
# 3)  أدوات JSON
# =============================================================================
def init_json_file(file_path, default_data):
    if not os.path.exists(file_path):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

def load_json_file(file_path, default=None):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return default if default is not None else {}

def save_json_file(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return True
    except Exception:
        return False

# =============================================================================
# 4)  إعدادات لوحة المالك (Flask)
# =============================================================================
def load_master_config():
    default_config = {
        'master_username': 'VEXpak2008X',
        'master_password_hash': hashlib.sha256('VEX 2008X'.encode()).hexdigest(),
        'port': 3178
    }
    if not os.path.exists(MASTER_CONFIG_FILE):
        save_json_file(MASTER_CONFIG_FILE, default_config)
        return default_config
    cfg = load_json_file(MASTER_CONFIG_FILE)
    if not cfg:
        return default_config
    for k, v in default_config.items():
        cfg.setdefault(k, v)
    return cfg

MASTER_CONFIG        = load_master_config()
MASTER_USERNAME      = MASTER_CONFIG.get('master_username', 'KING00')
MASTER_PASSWORD_HASH = MASTER_CONFIG.get('master_password_hash')
SERVER_START_TIME    = time.time()

# =============================================================================
# 6)  إنشاء المجلدات والملفات
# =============================================================================
for folder in [USERS_FOLDER, TEMP_FOLDER, BACKUPS_FOLDER]:
    os.makedirs(folder, exist_ok=True)

init_json_file(USERS_FILE, {})
init_json_file(PROCESSES_FILE, {})
init_json_file(SCHEDULES_FILE, {})
init_json_file(USER_SESSIONS_FILE, {})
init_json_file(PACKAGES_FILE, {'pip': [], 'apt': [], 'custom': []})
init_json_file(DOCKER_FILE, {'containers': [], 'images': []})
init_json_file(PORTS_FILE, {'ports': []})
init_json_file(ACTIVITY_FILE, {'events': []})
init_json_file(IPS_FILE, {'available': [], 'assigned': {}})

# تهيئة ملفات المالك
init_json_file(OWNER_CONFIG_FILE, {'telegram_token': '8845481168:AAFmH3-yfVT9qYnZMUfFgg4vvuEwf-0inaM', 'telegram_owner_id': '6617092470', 'bot_linked': True, 'panel_name': '<b>VEX </b> <span style="color:#29c7d3">VPS</span>', 'welcome_msg': 'مرحباً بك في لوحة التحكم'})
init_json_file(MAINTENANCE_FILE, {'enabled': False, 'message': 'الموقع تحت الصيانة، يرجى المحاولة لاحقاً'})
init_json_file(BOT_STATS_FILE, {'total_users': 0, 'total_servers': 0, 'active_bots': 0, 'zip_files': 0, 'last_updated': ''})
init_json_file(ANNOUNCE_FILE, {'list': []})

def load_owner_config():
    default = {'telegram_token': '8850691155:AAEM6Z_sYDnWCC64gEO4N_qSwcCsbCfJ2JA', 'telegram_owner_id': '6617092470', 'bot_linked': True, 'panel_name': '<b>VEX </b> <span style="color:#29c7d3">VPS</span>', 'welcome_msg': 'مرحباً بك في لوحة التحكم'}
    cfg = load_json_file(OWNER_CONFIG_FILE, default)
    for k, v in default.items():
        cfg.setdefault(k, v)
    return cfg

def save_owner_config(cfg):
    save_json_file(OWNER_CONFIG_FILE, cfg)

def load_maintenance():
    return load_json_file(MAINTENANCE_FILE, {'enabled': False, 'message': 'الموقع تحت الصيانة، يرجى المحاولة لاحقاً'})

def save_maintenance(data):
    save_json_file(MAINTENANCE_FILE, data)

def load_bot_stats():
    return load_json_file(BOT_STATS_FILE, {'total_users': 0, 'total_servers': 0, 'active_bots': 0, 'zip_files': 0, 'last_updated': ''})

def load_announcements():
    return load_json_file(ANNOUNCE_FILE, {'list': []})

def save_announcements(data):
    save_json_file(ANNOUNCE_FILE, data)

def escape_md2(text):
    return re.sub(r'([_*\[\]()~`>#+=|{}.!\-])', r'\\\1', str(text))

def load_ips():
    return load_json_file(IPS_FILE, {'available': [], 'assigned': {}})

def save_ips(data):
    save_json_file(IPS_FILE, data)

def assign_ip(username):
    data = load_ips()
    if username in data.get('assigned', {}):
        return data['assigned'][username]
    available = data.get('available', [])
    if available:
        ip = available.pop(0)
        data.setdefault('assigned', {})[username] = ip
        save_ips(data)
        return ip
    # توليد IP عشوائي تلقائياً لو البول فاضي
    ip = f"{random.randint(45,185)}.{random.randint(10,250)}.{random.randint(10,250)}.{random.randint(2,254)}"
    data.setdefault('assigned', {})[username] = ip
    save_ips(data)
    return ip

# =============================================================================
# 6.5)  قالب صفحة الصيانة
# =============================================================================
MAINTENANCE_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" crossorigin="anonymous">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>صيانة - VEX  VPS</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:"Inter","Segoe UI",sans-serif}
body{background:#1f2933;color:#d6dde3;min-height:100vh;display:flex;align-items:center;justify-content:center}
.maint-card{text-align:center;padding:50px 40px;background:#2b3a43;border:1px solid #3a4a55;border-radius:12px;max-width:500px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.maint-icon{font-size:80px;margin-bottom:20px;animation:spin 4s linear infinite}
@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
.maint-title{font-size:28px;font-weight:700;color:#fff;margin-bottom:10px}
.maint-sub{font-size:14px;color:#29c7d3;margin-bottom:24px;font-weight:600;text-transform:uppercase;letter-spacing:2px}
.maint-msg{font-size:16px;color:#9aa9b3;line-height:1.7;background:#1a242c;padding:16px 20px;border-radius:8px;border-left:4px solid #29c7d3}
.maint-footer{margin-top:24px;font-size:12px;color:#5a6c78}
.maint-footer a{color:#29c7d3;text-decoration:none}
.pulse{animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
</style>
</head>
<body>
<div class="maint-card">
  <div class="maint-icon"><i class="fas fa-cog"></i></div>
  <div class="maint-title"><b>MO <span style="color:#29c7d3">PANEL</span></b><br>صيانة مجدولة</div>
  <div class="maint-sub pulse"><i class="fas fa-wrench"></i> Under Maintenance</div>
  <div class="maint-msg">{{ message }}</div>
  <div class="maint-footer">Developed by Mo</div>
</div>
</body>
</html>
'''

# =============================================================================
# 7)  Flask App
# =============================================================================
app = Flask(__name__, static_folder=None)

@app.route('/manus-routes.json')
def manus_routes_manifest():
    return jsonify({'routes': [
        {'path': '/', 'title': 'PANELVEEX Servers'},
        {'path': '/login', 'title': 'PANELVEEX Login'},
        {'path': '/server/:server_id', 'title': 'PANELVEEX Server Panel'},
    ]})

def _get_persistent_secret_key():
    key_file = os.path.join(BASE_PATH, '.secret_key')
    try:
        os.makedirs(BASE_PATH, exist_ok=True)
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                k = f.read().strip()
                if k:
                    return k
        k = secrets.token_hex(64)
        with open(key_file, 'w') as f:
            f.write(k)
        return k
    except Exception:
        return secrets.token_hex(64)

app.secret_key = _get_persistent_secret_key()
app.permanent_session_lifetime = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Middleware لوضع الصيانة
@app.before_request
def check_maintenance():
    maint = load_maintenance()
    if not maint.get('enabled'):
        return None
    # السماح للمالك بالدخول دائماً
    if request.path in ['/login', '/logout'] or request.path.startswith('/api/'):
        return None
    if session.get('username') == MASTER_USERNAME:
        return None
    msg = maint.get('message', 'الموقع تحت الصيانة')
    return render_template_string(MAINTENANCE_TEMPLATE, message=msg), 503

# =============================================================================
# 8)  أدوات اللوحة (Activity feed محسّن لعرض على الواجهة)
# =============================================================================
def add_activity_event(username, action, details=""):
    """يضيف حدثاً للـ Activity feed (مثل صفحة Activity في Lunes Host)"""
    try:
        events = load_json_file(ACTIVITY_FILE, {'events': []}).get('events', [])
        events.insert(0, {
            'id': str(uuid.uuid4())[:8],
            'username': username,
            'action': action,
            'details': details,
            'ip': request.remote_addr if request else '-',
            'timestamp': datetime.now().isoformat(),
            'time_text': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        events = events[:300]  # احتفظ بأحدث 300 حدث
        save_json_file(ACTIVITY_FILE, {'events': events})
    except Exception:
        pass

def log_activity(username, action, details=""):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOGS_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] [{username}] {action} | {details}\n")
        add_activity_event(username, action, details)
    except Exception:
        pass

def load_users():            return load_json_file(USERS_FILE)
def save_users(u):           save_json_file(USERS_FILE, u)
def load_processes():        return load_json_file(PROCESSES_FILE)
def save_processes(p):       save_json_file(PROCESSES_FILE, p)
def load_schedules():        return load_json_file(SCHEDULES_FILE)
def save_schedules(s):       save_json_file(SCHEDULES_FILE, s)
def load_user_sessions():    return load_json_file(USER_SESSIONS_FILE)
def save_user_sessions(s):   save_json_file(USER_SESSIONS_FILE, s)
def load_packages():         return load_json_file(PACKAGES_FILE)
def save_packages(p):        save_json_file(PACKAGES_FILE, p)
def load_ports():            return load_json_file(PORTS_FILE, {'ports': []}).get('ports', [])
def save_ports(p):           save_json_file(PORTS_FILE, {'ports': p})

def get_user_path(username):
    if username == MASTER_USERNAME:
        return BASE_PATH
    return os.path.join(USERS_FOLDER, username)

def ensure_user_folder(username):
    if username == MASTER_USERNAME:
        return
    p = get_user_path(username)
    os.makedirs(p, exist_ok=True)

def is_path_allowed(username, requested_path):
    """تحقق صارم من مسار الملف — يمنع path traversal و symlink escape"""
    if username == MASTER_USERNAME:
        return True
    if not requested_path:
        return False
    # منع path traversal المباشر
    norm = os.path.normpath(str(requested_path))
    if '..' in norm.split(os.sep):
        return False
    # مقارنة المسارات الحقيقية (يحل symlinks)
    user_path = get_user_path(username)
    try:
        real_req  = os.path.realpath(norm)
        real_user = os.path.realpath(user_path)
        try:
            if os.path.commonpath([real_req, real_user]) != real_user:
                return False
        except ValueError:
            return False
        # منع الوصول لملفات النظام الحساسة حتى لو كانت داخل المسار
        FORBIDDEN = ['/etc/', '/root/', '/proc/', '/sys/', '/dev/', '/run/']
        for f in FORBIDDEN:
            if real_req.startswith(f):
                return False
        return True
    except Exception:
        return False

def can_user_login(username):
    sessions = load_user_sessions()
    users = load_users()
    if username not in users:
        return False
    max_s = users[username].get('max_sessions', 999) if isinstance(users[username], dict) else 999
    return sessions.get(username, 0) < max_s

def register_session(username):
    sessions = load_user_sessions()
    sessions[username] = sessions.get(username, 0) + 1
    save_user_sessions(sessions)

def unregister_session(username):
    sessions = load_user_sessions()
    if username in sessions:
        sessions[username] = max(0, sessions[username] - 1)
        save_user_sessions(sessions)

def get_system_stats():
    try:
        net = psutil.net_io_counters()
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'memory_used_mb': psutil.virtual_memory().used / (1024**2),
            'memory_total_mb': psutil.virtual_memory().total / (1024**2),
            'memory_used_gb': psutil.virtual_memory().used / (1024**3),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'disk_percent': psutil.disk_usage('/').percent,
            'disk_used_mb': psutil.disk_usage('/').used / (1024**2),
            'disk_used_gb': psutil.disk_usage('/').used / (1024**3),
            'disk_total_gb': psutil.disk_usage('/').total / (1024**3),
            'uptime': int(time.time() - SERVER_START_TIME),
            'uptime_system': int(time.time() - psutil.boot_time()),
            'net_in_kb': net.bytes_recv / 1024,
            'net_out_kb': net.bytes_sent / 1024,
            'platform': platform.platform(),
            'hostname': socket.gethostname(),
            'public_ip': requests.get('https://api.ipify.org', timeout=2).text if 'requests' in globals() else 'N/A'
        }
    except Exception:
        return {}

def format_uptime(secs):
    secs = int(secs or 0)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h}h {m}m {s}s"

# =============================================================================
# 9)  أدوات تشغيل الملفات (كاملة مع run/stop/output/input)
# =============================================================================
running_processes = {}
running_files     = {}
file_processes    = {}
port_processes    = {}  # للبورتات الإضافية

def extract_and_find_main(zip_path, extract_to):
    """فك ZIP داخل مجلد المستخدم فقط، مع منع Zip Slip والروابط الرمزية."""
    try:
        root = os.path.realpath(extract_to)
        os.makedirs(root, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as z:
            total = 0
            for info in z.infolist():
                name = info.filename.replace('\\', '/')
                parts = [part for part in name.split('/') if part not in ('', '.')]
                if not parts or name.startswith('/') or any(part == '..' for part in parts):
                    raise ValueError('unsafe archive path')
                if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError('symlink in archive is not allowed')
                total += info.file_size
                if total > 512 * 1024 * 1024:
                    raise ValueError('archive too large')
                target = os.path.realpath(os.path.join(root, *parts))
                if os.path.commonpath([root, target]) != root:
                    raise ValueError('unsafe archive path')
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with z.open(info, 'r') as src, open(target, 'wb') as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
        main_files = ['main.py', 'app.py', 'bot.py', 'run.py', 'start.py', 'index.py']
        for root_dir, dirs, files in os.walk(root):
            for name in files:
                if name.lower() in main_files:
                    return os.path.join(root_dir, name)
        for root_dir, dirs, files in os.walk(root):
            for name in files:
                if name.endswith(('.py', '.js', '.sh')):
                    return os.path.join(root_dir, name)
    except Exception:
        return None
    return None
def validate_python_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().strip()
        if not content:
            return False, "File is empty"
        try:
            ast.parse(content)
            return True, "Valid Python code"
        except SyntaxError as e:
            return False, f"Python syntax error: {e}"
    except Exception:
        return True, ""

def get_run_command(filepath):
    ext = filepath.split('.')[-1].lower()
    commands = {
        'py':   f'python3 -u "{filepath}"',
        'js':   f'node "{filepath}"',
        'php':  f'php "{filepath}"',
        'sh':   f'bash "{filepath}"',
        'bash': f'bash "{filepath}"',
        'rb':   f'ruby "{filepath}"',
        'pl':   f'perl "{filepath}"',
        'lua':  f'lua "{filepath}"',
        'go':   f'go run "{filepath}"',
        'java': f'java "{filepath}"',
        'jar':  f'java -jar "{filepath}"',
        'c':    f'gcc "{filepath}" -o "{os.path.splitext(filepath)[0]}" && "{os.path.splitext(filepath)[0]}"',
        'cpp':  f'g++ "{filepath}" -o "{os.path.splitext(filepath)[0]}" && "{os.path.splitext(filepath)[0]}"',
        'rs':   f'rustc "{filepath}" && "{os.path.splitext(filepath)[0]}"',
        'dart': f'dart "{filepath}"',
        'r':    f'Rscript "{filepath}"',
        'jl':   f'julia "{filepath}"',
    }
    return commands.get(ext, f'python3 -u "{filepath}"')

def read_process_output(proc_id, process, max_lines=2000, store=None):
    store = store if store is not None else file_processes
    output_buffer = deque(maxlen=max_lines)
    try:
        for line in iter(process.stdout.readline, ''):
            if proc_id not in store:
                break
            output_buffer.append(line.rstrip('\n'))
            store[proc_id]['output'] = list(output_buffer)
    except Exception:
        pass

def auto_install_dependencies(filepath):
    """
    كاشف ذكي للمكتبات — يدعم Python/JS/TS/Ruby/PHP/Perl/Lua
    يقرأ ملفات التكوين (requirements.txt, package.json, Gemfile...)
    ويكتشف كل import ويثبّت المفقود تلقائياً مع PyPI fallback للباكجات المجهولة.
    """
    installed, failed = [], []
    ext = os.path.splitext(filepath)[1].lower()
    work_dir = os.path.dirname(filepath)

    # ── دالة مساعدة: pip install مع fallback flags ──────────────────────────
    def pip_install(pkg, timeout=240):
        for flag in ['--break-system-packages', '--user', '']:
            cmd = [sys.executable, '-m', 'pip', 'install', '--quiet']
            if flag:
                cmd.append(flag)
            cmd.append(pkg)
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    # ── دالة مساعدة: البحث في PyPI API ──────────────────────────────────────
    def pypi_find(import_name):
        candidates = [
            import_name,
            import_name.replace('_', '-'),
            'python-' + import_name.replace('_', '-'),
            import_name.replace('_', '-') + '-python',
            'py' + import_name.replace('_', '-'),
        ]
        for name in candidates:
            try:
                r = requests.get(
                    'https://pypi.org/pypi/' + name + '/json',
                    timeout=8, headers={'User-Agent': 'panel/1.0'})
                if r.status_code == 200:
                    return name
            except Exception:
                pass
        return None

    # ── إيجاد ملف تكوين في الدليل الحالي أو أعلاه ──────────────────────────
    def _find_config(names, start_dir, levels=4):
        cur = start_dir
        for _ in range(levels):
            for n in names:
                p = os.path.join(cur, n)
                if os.path.exists(p):
                    return p
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return None

    # ══════════════════════════════════════════════════════════════════════════
    # 1) ملفات التكوين الخاصة بكل لغة
    # ══════════════════════════════════════════════════════════════════════════

    # Python: requirements.txt
    req_path = _find_config(
        ['requirements.txt', 'requirements-dev.txt', 'requirements_dev.txt'], work_dir)
    if req_path:
        try:
            r = subprocess.run(
                [sys.executable, '-m', 'pip', 'install',
                 '--break-system-packages', '--quiet', '-r', req_path],
                capture_output=True, text=True, timeout=300)
            (installed if r.returncode == 0 else failed).append(
                '[req] ' + os.path.basename(req_path))
        except Exception as e:
            failed.append('[req] ' + str(e))

    # Python: setup.py / pyproject.toml / Pipfile
    for cfg in ['setup.py', 'pyproject.toml', 'Pipfile']:
        cfg_path = _find_config([cfg], work_dir)
        if cfg_path:
            try:
                r = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install',
                     '--break-system-packages', '--quiet',
                     '-e', os.path.dirname(cfg_path)],
                    capture_output=True, text=True, timeout=300)
                if r.returncode == 0:
                    installed.append('[' + cfg + ']')
            except Exception:
                pass
            break

    # JS/TS: package.json
    if ext in ('.js', '.mjs', '.cjs', '.ts', '.tsx'):
        pkg_json = _find_config(['package.json'], work_dir)
        if pkg_json:
            npm = shutil.which('npm') or shutil.which('bun') or shutil.which('yarn')
            if npm:
                try:
                    r = subprocess.run(
                        [npm, 'install', '--silent'],
                        capture_output=True, text=True,
                        cwd=os.path.dirname(pkg_json), timeout=300)
                    (installed if r.returncode == 0 else failed).append('[package.json]')
                except Exception as e:
                    failed.append('[npm] ' + str(e))

    # Ruby: Gemfile
    if ext == '.rb':
        gemfile = _find_config(['Gemfile'], work_dir)
        if gemfile:
            bundler = shutil.which('bundle')
            if bundler:
                try:
                    r = subprocess.run(
                        [bundler, 'install'],
                        capture_output=True, text=True,
                        cwd=os.path.dirname(gemfile), timeout=300)
                    (installed if r.returncode == 0 else failed).append('[Gemfile]')
                except Exception as e:
                    failed.append('[bundle] ' + str(e))

    # PHP: composer.json
    if ext == '.php':
        comp = _find_config(['composer.json'], work_dir)
        if comp:
            composer = shutil.which('composer')
            if composer:
                try:
                    r = subprocess.run(
                        [composer, 'install', '--no-interaction'],
                        capture_output=True, text=True,
                        cwd=os.path.dirname(comp), timeout=300)
                    (installed if r.returncode == 0 else failed).append('[composer.json]')
                except Exception as e:
                    failed.append('[composer] ' + str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # 2) قائمة المكتبات القياسية لـ Python
    # ══════════════════════════════════════════════════════════════════════════
    try:
        _stdlib = set(sys.stdlib_module_names)
    except AttributeError:
        _stdlib = {
            '__future__', '_thread', 'abc', 'aifc', 'argparse', 'array', 'ast',
            'asynchat', 'asyncio', 'asyncore', 'atexit', 'audioop', 'base64',
            'bdb', 'binascii', 'binhex', 'bisect', 'builtins', 'bz2', 'calendar',
            'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs', 'codeop',
            'colorsys', 'compileall', 'concurrent', 'configparser', 'contextlib',
            'contextvars', 'copy', 'copyreg', 'cProfile', 'csv', 'ctypes',
            'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib',
            'dis', 'distutils', 'doctest', 'email', 'encodings', 'enum', 'errno',
            'faulthandler', 'fcntl', 'filecmp', 'fileinput', 'fnmatch',
            'fractions', 'ftplib', 'functools', 'gc', 'getopt', 'getpass',
            'gettext', 'glob', 'grp', 'gzip', 'hashlib', 'heapq', 'hmac',
            'html', 'http', 'idlelib', 'imaplib', 'imghdr', 'imp', 'importlib',
            'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword',
            'lib2to3', 'linecache', 'locale', 'logging', 'lzma', 'mailbox',
            'mailcap', 'marshal', 'math', 'mimetypes', 'mmap', 'modulefinder',
            'multiprocessing', 'netrc', 'nis', 'nntplib', 'numbers', 'operator',
            'optparse', 'os', 'ossaudiodev', 'parser', 'pathlib', 'pdb',
            'pickle', 'pickletools', 'pipes', 'pkgutil', 'platform', 'plistlib',
            'poplib', 'posix', 'posixpath', 'pprint', 'profile', 'pstats', 'pty',
            'pwd', 'py_compile', 'pyclbr', 'pydoc', 'queue', 'quopri', 'random',
            're', 'readline', 'reprlib', 'resource', 'rlcompleter', 'runpy',
            'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex',
            'shutil', 'signal', 'site', 'smtpd', 'smtplib', 'sndhdr', 'socket',
            'socketserver', 'spwd', 'sqlite3', 'ssl', 'stat', 'statistics',
            'string', 'stringprep', 'struct', 'subprocess', 'sunau', 'symtable',
            'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile', 'telnetlib',
            'tempfile', 'termios', 'test', 'textwrap', 'threading', 'time',
            'timeit', 'tkinter', 'token', 'tokenize', 'trace', 'traceback',
            'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types', 'typing',
            'unicodedata', 'unittest', 'urllib', 'uu', 'uuid', 'venv',
            'warnings', 'wave', 'weakref', 'webbrowser', 'winreg', 'winsound',
            'wsgiref', 'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile',
            'zipimport', 'zlib', 'zoneinfo',
        }
    # أضف المكتبات المثبّتة مسبقاً مع النظام
    _stdlib.update({
        'flask', 'requests', 'psutil', 'werkzeug', 'jinja2', 'click',
        'itsdangerous', 'markupsafe', 'certifi', 'charset_normalizer',
        'urllib3', 'idna',
    })

    # ══════════════════════════════════════════════════════════════════════════
    # 3) خريطة شاملة: import_name → pip_package_name
    # ══════════════════════════════════════════════════════════════════════════
    PACKAGE_MAP = {
        # ── Telegram / Chat ──────────────────────────────────────────────────
        'telegram':             'python-telegram-bot',
        'telebot':              'pyTelegramBotAPI',
        'aiogram':              'aiogram',
        'pyrogram':             'pyrogram',
        'telethon':             'Telethon',
        'tgcrypto':             'tgcrypto',
        'discord':              'discord.py',
        'nextcord':             'nextcord',
        'disnake':              'disnake',
        'hikari':               'hikari',
        'twitchio':             'twitchio',
        'slack_sdk':            'slack-sdk',
        'slack':                'slackclient',
        'tweepy':               'tweepy',
        'twilio':               'twilio',
        'vk_api':               'vk-api',
        'vkbottle':             'vkbottle',
        'line_bot_sdk':         'line-bot-sdk',
        'mattermostdriver':     'mattermostdriver',
        # ── HTTP / Web ───────────────────────────────────────────────────────
        'aiohttp':              'aiohttp',
        'httpx':                'httpx',
        'httpcore':             'httpcore',
        'httplib2':             'httplib2',
        'curl_cffi':            'curl_cffi',
        'pycurl':               'pycurl',
        'bs4':                  'beautifulsoup4',
        'lxml':                 'lxml',
        'html5lib':             'html5lib',
        'scrapy':               'Scrapy',
        'playwright':           'playwright',
        'selenium':             'selenium',
        'pyppeteer':            'pyppeteer',
        'mechanize':            'mechanize',
        'aiofiles':             'aiofiles',
        'websockets':           'websockets',
        'websocket':            'websocket-client',
        'socketio':             'python-socketio',
        'uvicorn':              'uvicorn',
        'gunicorn':             'gunicorn',
        'fastapi':              'fastapi',
        'starlette':            'starlette',
        'quart':                'quart',
        'sanic':                'sanic',
        'tornado':              'tornado',
        'bottle':               'bottle',
        'cherrypy':             'CherryPy',
        'falcon':               'falcon',
        'django':               'Django',
        'rest_framework':       'djangorestframework',
        'channels':             'channels',
        'grpc':                 'grpcio',
        'nest_asyncio':         'nest_asyncio',
        'anyio':                'anyio',
        'trio':                 'trio',
        'multipart':            'python-multipart',
        'pydantic':             'pydantic',
        'attrs':                'attrs',
        'attr':                 'attrs',
        'marshmallow':          'marshmallow',
        'orjson':               'orjson',
        'ujson':                'ujson',
        'msgpack':              'msgpack',
        'cbor2':                'cbor2',
        'humps':                'pyhumps',
        # ── Config / Env ─────────────────────────────────────────────────────
        'dotenv':               'python-dotenv',
        'decouple':             'python-decouple',
        'yaml':                 'PyYAML',
        'toml':                 'toml',
        'tomllib':              'tomli',
        'dynaconf':             'dynaconf',
        'environs':             'environs',
        'configobj':            'configobj',
        # ── Database ─────────────────────────────────────────────────────────
        'motor':                'motor',
        'pymongo':              'pymongo',
        'mongoengine':          'mongoengine',
        'redis':                'redis',
        'aioredis':             'aioredis',
        'psycopg2':             'psycopg2-binary',
        'psycopg':              'psycopg2-binary',
        'asyncpg':              'asyncpg',
        'aiopg':                'aiopg',
        'mysql':                'mysql-connector-python',
        'MySQLdb':              'mysqlclient',
        'pymysql':              'PyMySQL',
        'aiomysql':             'aiomysql',
        'cx_Oracle':            'cx_Oracle',
        'pyodbc':               'pyodbc',
        'tortoise':             'tortoise-orm',
        'databases':            'databases',
        'sqlalchemy':           'SQLAlchemy',
        'alembic':              'alembic',
        'flask_sqlalchemy':     'Flask-SQLAlchemy',
        'flask_migrate':        'Flask-Migrate',
        'flask_login':          'Flask-Login',
        'flask_wtf':            'Flask-WTF',
        'flask_cors':           'Flask-Cors',
        'flask_jwt_extended':   'Flask-JWT-Extended',
        'flask_mail':           'Flask-Mail',
        'flask_limiter':        'Flask-Limiter',
        'flask_socketio':       'Flask-SocketIO',
        'flask_bcrypt':         'Flask-Bcrypt',
        'peewee':               'peewee',
        'tinydb':               'tinydb',
        'pickledb':             'pickledb',
        'dataset':              'dataset',
        'sqlite_utils':         'sqlite-utils',
        'aiosqlite':            'aiosqlite',
        'elasticsearch':        'elasticsearch',
        'opensearchpy':         'opensearch-py',
        'cassandra':            'cassandra-driver',
        'couchdb':              'CouchDB',
        'influxdb':             'influxdb',
        'influxdb_client':      'influxdb-client',
        # ── Data Science / ML ────────────────────────────────────────────────
        'numpy':                'numpy',
        'np':                   'numpy',
        'pandas':               'pandas',
        'pd':                   'pandas',
        'matplotlib':           'matplotlib',
        'seaborn':              'seaborn',
        'plotly':               'plotly',
        'bokeh':                'bokeh',
        'altair':               'altair',
        'scipy':                'scipy',
        'sklearn':              'scikit-learn',
        'skimage':              'scikit-image',
        'xgboost':              'xgboost',
        'lightgbm':             'lightgbm',
        'catboost':             'catboost',
        'torch':                'torch',
        'torchvision':          'torchvision',
        'torchaudio':           'torchaudio',
        'tensorflow':           'tensorflow',
        'keras':                'keras',
        'jax':                  'jax',
        'flax':                 'flax',
        'transformers':         'transformers',
        'diffusers':            'diffusers',
        'accelerate':           'accelerate',
        'peft':                 'peft',
        'bitsandbytes':         'bitsandbytes',
        'langchain':            'langchain',
        'langchain_core':       'langchain-core',
        'langchain_community':  'langchain-community',
        'openai':               'openai',
        'anthropic':            'anthropic',
        'groq':                 'groq',
        'cohere':               'cohere',
        'google_generativeai':  'google-generativeai',
        'tiktoken':             'tiktoken',
        'nltk':                 'nltk',
        'spacy':                'spacy',
        'gensim':               'gensim',
        'textblob':             'textblob',
        'stanza':               'stanza',
        'wordcloud':            'wordcloud',
        'statsmodels':          'statsmodels',
        'sympy':                'sympy',
        'networkx':             'networkx',
        'igraph':               'python-igraph',
        'numba':                'numba',
        'dask':                 'dask',
        'ray':                  'ray',
        'joblib':               'joblib',
        'tqdm':                 'tqdm',
        'alive_progress':       'alive-progress',
        'rich':                 'rich',
        'typer':                'typer',
        'loguru':               'loguru',
        'pyarrow':              'pyarrow',
        'polars':               'polars',
        'openpyxl':             'openpyxl',
        'xlrd':                 'xlrd',
        'xlwt':                 'xlwt',
        'xlsxwriter':           'XlsxWriter',
        'tabulate':             'tabulate',
        'prettytable':          'prettytable',
        'colorama':             'colorama',
        'termcolor':            'termcolor',
        'loguru':               'loguru',
        'structlog':            'structlog',
        'icecream':             'icecream',
        # ── Image / Media ────────────────────────────────────────────────────
        'PIL':                  'Pillow',
        'pillow':               'Pillow',
        'cv2':                  'opencv-python',
        'cv':                   'opencv-python',
        'imageio':              'imageio',
        'wand':                 'Wand',
        'cairosvg':             'cairosvg',
        'qrcode':               'qrcode',
        'barcode':              'python-barcode',
        'pyzbar':               'pyzbar',
        'yt_dlp':               'yt-dlp',
        'youtube_dl':           'youtube-dl',
        'pytube':               'pytube',
        'mutagen':              'mutagen',
        'pydub':                'pydub',
        'sounddevice':          'sounddevice',
        'pyaudio':              'PyAudio',
        'playsound':            'playsound',
        'gtts':                 'gTTS',
        'pygame':               'pygame',
        'pyglet':               'pyglet',
        'moviepy':              'moviepy',
        'ffmpeg':               'ffmpeg-python',
        'imageio_ffmpeg':       'imageio-ffmpeg',
        'svgwrite':             'svgwrite',
        'reportlab':            'reportlab',
        'fpdf':                 'fpdf2',
        'fpdf2':                'fpdf2',
        'PyPDF2':               'PyPDF2',
        'pypdf':                'pypdf',
        'pdfminer':             'pdfminer.six',
        'pdfplumber':           'pdfplumber',
        'pdf2image':            'pdf2image',
        'docx':                 'python-docx',
        'docx2txt':             'docx2txt',
        'pptx':                 'python-pptx',
        'odf':                  'odfpy',
        'pyautogui':            'pyautogui',
        'pynput':               'pynput',
        'keyboard':             'keyboard',
        'mouse':                'mouse',
        'pyperclip':            'pyperclip',
        # ── Crypto / Security ────────────────────────────────────────────────
        'crypto':               'pycryptodome',
        'Crypto':               'pycryptodome',
        'Cryptodome':           'pycryptodomex',
        'nacl':                 'PyNaCl',
        'argon2':               'argon2-cffi',
        'bcrypt':               'bcrypt',
        'cryptography':         'cryptography',
        'jwt':                  'PyJWT',
        'jose':                 'python-jose',
        'passlib':              'passlib',
        'pyotp':                'pyotp',
        'paramiko':             'paramiko',
        'fabric':               'fabric',
        'invoke':               'invoke',
        'pysftp':               'pysftp',
        # ── Async / Task Queues ──────────────────────────────────────────────
        'gevent':               'gevent',
        'greenlet':             'greenlet',
        'celery':               'celery',
        'rq':                   'rq',
        'dramatiq':             'dramatiq',
        'apscheduler':          'APScheduler',
        'schedule':             'schedule',
        'croniter':             'croniter',
        # ── Cloud / DevOps ───────────────────────────────────────────────────
        'boto3':                'boto3',
        'botocore':             'botocore',
        'googleapiclient':      'google-api-python-client',
        'kubernetes':           'kubernetes',
        'docker':               'docker',
        'sentry_sdk':           'sentry-sdk',
        'prometheus_client':    'prometheus-client',
        'opentelemetry':        'opentelemetry-api',
        # ── CLI / Terminal ───────────────────────────────────────────────────
        'click':                'click',
        'docopt':               'docopt',
        'fire':                 'fire',
        'plumbum':              'plumbum',
        'blessed':              'blessed',
        'urwid':                'urwid',
        'prompt_toolkit':       'prompt_toolkit',
        'questionary':          'questionary',
        'inquirer':             'inquirer',
        'halo':                 'halo',
        'colorlog':             'colorlog',
        'sh':                   'sh',
        'pexpect':              'pexpect',
        'ptyprocess':           'ptyprocess',
        # ── Testing ──────────────────────────────────────────────────────────
        'pytest':               'pytest',
        'hypothesis':           'hypothesis',
        'faker':                'Faker',
        'factory_boy':          'factory-boy',
        'responses':            'responses',
        'freezegun':            'freezegun',
        'coverage':             'coverage',
        'pylint':               'pylint',
        'flake8':               'flake8',
        'black':                'black',
        'isort':                'isort',
        'mypy':                 'mypy',
        # ── Parsing / Text ───────────────────────────────────────────────────
        'pyparsing':            'pyparsing',
        'lark':                 'lark',
        'regex':                'regex',
        'unidecode':            'Unidecode',
        'chardet':              'chardet',
        'charset_normalizer':   'charset-normalizer',
        'ftfy':                 'ftfy',
        'phonenumbers':         'phonenumbers',
        'arrow':                'arrow',
        'dateutil':             'python-dateutil',
        'pendulum':             'pendulum',
        'pytz':                 'pytz',
        'babel':                'Babel',
        'humanize':             'humanize',
        'num2words':            'num2words',
        'langdetect':           'langdetect',
        'deep_translator':      'deep-translator',
        'googletrans':          'googletrans',
        'translate':            'translate',
        # ── Finance ──────────────────────────────────────────────────────────
        'yfinance':             'yfinance',
        'ccxt':                 'ccxt',
        'stripe':               'stripe',
        'paypalrestsdk':        'paypalrestsdk',
        'alpaca_trade_api':     'alpaca-trade-api',
        'backtrader':           'backtrader',
        'pandas_datareader':    'pandas-datareader',
        'pycoingecko':          'pycoingecko',
        'alpha_vantage':        'alpha_vantage',
        # ── GUI / Desktop ────────────────────────────────────────────────────
        'PyQt5':                'PyQt5',
        'PyQt6':                'PyQt6',
        'PySide6':              'PySide6',
        'wx':                   'wxPython',
        'customtkinter':        'customtkinter',
        'ttkbootstrap':         'ttkbootstrap',
        'kivy':                 'kivy',
        'textual':              'textual',
        'streamlit':            'streamlit',
        'gradio':               'gradio',
        'dash':                 'dash',
        'nicegui':              'nicegui',
        'eel':                  'eel',
        'pywebview':            'pywebview',
        # ── Misc ─────────────────────────────────────────────────────────────
        'cachetools':           'cachetools',
        'diskcache':            'diskcache',
        'appdirs':              'appdirs',
        'platformdirs':         'platformdirs',
        'send2trash':           'Send2Trash',
        'watchdog':             'watchdog',
        'nuitka':               'Nuitka',
        'pyinstaller':          'pyinstaller',
        'stdnum':               'python-stdnum',
        'vaex':                 'vaex',
        'fastparquet':          'fastparquet',
        'comtypes':             'comtypes',
    }

    # ══════════════════════════════════════════════════════════════════════════
    # 4) استخراج أسماء الحزم من الملف حسب نوعه
    # ══════════════════════════════════════════════════════════════════════════
    packages = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            src = f.read()

        if ext == '.py':
            # AST parse أولاً (أدق) ثم regex كـ fallback
            try:
                tree = ast.parse(src)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for a in node.names:
                            packages.append(a.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if (node.level or 0) == 0 and node.module:
                            packages.append(node.module.split('.')[0])
            except SyntaxError:
                packages = re.findall(
                    r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)',
                    src, re.MULTILINE)

        elif ext in ('.js', '.mjs', '.cjs'):
            packages += re.findall(
                r"require\s*\(\s*[\"']([^\"'./][^\"']*)[\"']\s*\)", src)
            packages += re.findall(
                r"from\s+[\"']([^\"'./][^\"'.][^\"']*)[\"']", src)

        elif ext in ('.ts', '.tsx'):
            packages += re.findall(
                r"from\s+[\"']([^\"'./][^\"'.][^\"']*)[\"']", src)
            packages += re.findall(
                r"require\s*\(\s*[\"']([^\"'./][^\"']*)[\"']\s*\)", src)

        elif ext == '.rb':
            gems = re.findall(r"require\s+['\"]([^'\"]+)['\"]", src)
            ruby_std = {
                'json', 'yaml', 'csv', 'net/http', 'uri', 'open-uri',
                'fileutils', 'pathname', 'date', 'time', 'digest', 'base64',
                'socket', 'thread', 'timeout', 'ostruct', 'logger', 'pp',
                'benchmark', 'tmpdir', 'rake', 'erb', 'cgi', 'optparse',
                'singleton', 'forwardable', 'observer', 'monitor', 'mutex',
            }
            gem_exe = shutil.which('gem')
            if gem_exe:
                for gem in set(gems):
                    top = gem.split('/')[0]
                    if top not in ruby_std:
                        try:
                            chk = subprocess.run(
                                [gem_exe, 'list', top],
                                capture_output=True, text=True, timeout=15)
                            if top not in chk.stdout:
                                r2 = subprocess.run(
                                    [gem_exe, 'install', top, '--no-document'],
                                    capture_output=True, text=True, timeout=120)
                                (installed if r2.returncode == 0 else failed).append(top)
                        except Exception:
                            failed.append(top)
            return {'installed': installed, 'failed': failed}

        elif ext == '.php':
            uses = re.findall(r'use\s+([\w\\]+)', src)
            psr = [u.split('\\')[0] for u in uses if '\\' in u]
            php_std = {
                'PDO', 'Exception', 'DateTime', 'ArrayObject', 'SplStack',
                'stdClass', 'ArrayAccess', 'Countable', 'Iterator',
                'Traversable', 'InvalidArgumentException', 'RuntimeException',
            }
            comp = shutil.which('composer')
            if comp:
                for pkg in set(psr):
                    if pkg not in php_std:
                        failed.append('[php/' + pkg + ': composer install required]')
            return {'installed': installed, 'failed': failed}

        elif ext == '.pl':
            mods = re.findall(r'^use\s+([A-Za-z][\w:]+)', src, re.MULTILINE)
            perl_core = {
                'strict', 'warnings', 'Data::Dumper', 'Scalar::Util',
                'List::Util', 'POSIX', 'Carp', 'File::Basename', 'File::Path',
                'Getopt::Long', 'Storable', 'Encode', 'utf8', 'overload',
                'constant', 'vars', 'base', 'Exporter', 'Fcntl', 'IO::File',
            }
            cpan = shutil.which('cpanm') or shutil.which('cpan')
            if cpan:
                for mod in set(mods):
                    if mod not in perl_core:
                        try:
                            r2 = subprocess.run(
                                [cpan, mod],
                                capture_output=True, text=True, timeout=120)
                            (installed if r2.returncode == 0 else failed).append(mod)
                        except Exception:
                            failed.append(mod)
            return {'installed': installed, 'failed': failed}

        elif ext == '.lua':
            mods = re.findall(r"require\s*['\"]([^'\"]+)['\"]", src)
            lua_std = {
                'string', 'table', 'math', 'io', 'os', 'package', 'debug',
                'coroutine', 'utf8', 'bit32', 'jit', 'ffi',
            }
            luarocks = shutil.which('luarocks')
            if luarocks:
                for mod in set(mods):
                    if mod not in lua_std:
                        try:
                            r2 = subprocess.run(
                                [luarocks, 'install', mod],
                                capture_output=True, text=True, timeout=120)
                            (installed if r2.returncode == 0 else failed).append(mod)
                        except Exception:
                            failed.append(mod)
            return {'installed': installed, 'failed': failed}

    except Exception as e:
        failed.append('[parse-error] ' + str(e))

    # ══════════════════════════════════════════════════════════════════════════
    # 5) تثبيت حزم Python المفقودة (مع PyPI fallback ذكي)
    # ══════════════════════════════════════════════════════════════════════════
    seen = set()
    for pkg in packages:
        if not pkg or pkg.startswith('.') or pkg.startswith('_') or pkg in _stdlib:
            continue
        if pkg in seen:
            continue
        seen.add(pkg)

        # تحقق: هل المكتبة مثبّتة فعلاً؟
        try:
            __import__(pkg)
            continue
        except ImportError:
            pass
        except Exception:
            continue

        # ابحث في الخريطة الشاملة أولاً
        pip_name = PACKAGE_MAP.get(pkg)
        if pip_name:
            if pip_install(pip_name):
                installed.append(pip_name)
            else:
                failed.append(pip_name)
            continue

        # جرّب الاسم مباشرةً
        if pip_install(pkg):
            installed.append(pkg)
            continue

        # جرّب تحويلات شائعة للاسم
        alt_names = [
            pkg.replace('_', '-'),
            'python-' + pkg.replace('_', '-'),
            'py' + pkg.lower(),
            pkg.lower(),
        ]
        success = False
        for alt in alt_names:
            if alt in (pkg, ''):
                continue
            if pip_install(alt):
                installed.append(alt)
                success = True
                break
        if success:
            continue

        # آخر محاولة: البحث في PyPI API
        try:
            found = pypi_find(pkg)
            if found and found not in alt_names and found != pkg:
                if pip_install(found):
                    installed.append(found)
                    continue
        except Exception:
            pass

        failed.append(pkg)

    return {'installed': installed, 'failed': failed}


# =============================================================================
# 10)  ديكورات الـ Flask
# =============================================================================
def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'logged_in' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Session expired'}), 401
            return redirect('/login')
        return f(*a, **kw)
    return w

def master_required(f):
    @wraps(f)
    def w(*a, **kw):
        if session.get('username') != MASTER_USERNAME:
            return jsonify({'success': False, 'error': 'Master only'}), 403
        return f(*a, **kw)
    return w

# =============================================================================
# 11)  قالب تسجيل الدخول (شكل Pterodactyl/Lunes Host)
# =============================================================================
LOGIN_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>PANELVEEX — Login</title>
<style>
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:#050505;color:#e8e8e8;font-family:Inter,"Segoe UI",Tahoma,sans-serif;overflow-x:hidden}.login-container{width:100%;max-width:720px;margin:0 auto;padding:52px 8px 0}.login-title{font-size:58px;line-height:1.12;font-weight:400;margin:0 0 38px 88px;color:#f2f2f2}.card{background:#101010;border:2px solid #222;width:100%;padding:42px 47px 38px}.brand{text-align:left;margin-bottom:52px}.brand h1{font-size:68px;line-height:1;margin:0;color:#f2f2f2;font-weight:700;letter-spacing:15px}.field{margin-bottom:50px}.field label{display:block;color:#aaa;font-size:22px;letter-spacing:1px;margin-bottom:13px}.field input{width:100%;height:88px;background:#101010;border:2px solid #242424;color:#fff;font-size:22px;padding:0 14px;outline:none;border-radius:0}.field input:focus{border-color:#4f78b5}.btn{width:100%;height:105px;border:0;border-radius:0;background:#527ab5;color:#fff;font-size:28px;cursor:pointer;margin-top:-3px}.btn:hover{background:#5d86c2}.error{margin-top:18px;padding:12px;border:1px solid #733;background:#251010;color:#ff9b9b;text-align:center;font-size:16px}.foot{text-align:center;color:#696969;font-size:20px;margin-top:34px}@media(max-width:520px){.login-container{padding:50px 4px 0}.login-title{font-size:30px;margin:0 0 23px 44px}.card{padding:31px 24px 24px}.brand{margin-bottom:33px}.brand h1{font-size:35px;letter-spacing:10px}.field{margin-bottom:31px}.field label{font-size:15px;margin-bottom:8px}.field input{height:44px;font-size:16px}.btn{height:53px;font-size:18px}.foot{font-size:13px;margin-top:21px}}
</style></head>
<body><div class="login-container"><div class="login-title">Login to Continue</div><div class="card"><div class="brand"><h1>PANELVEEX</h1></div><form method="post" action="/login"><div class="field"><label>USERNAME OR EMAIL</label><input type="text" name="username" required autofocus></div><div class="field"><label>PASSWORD</label><input type="password" name="password" required></div><button class="btn" type="submit">LOGIN</button>{% if error %}<div class="error">{{ error }}</div>{% endif %}</form></div><div class="foot">♘ king panelveex © 2015 - 2026</div></div></body></html>
'''



# =============================================================================
# 12)  القالب الرئيسي (شكل Pterodactyl / Lunes Host)
# =============================================================================

# =============================================================================
# 11.5) قائمة السيرفرات — نمط PANELVEEX/Pterodactyl
# =============================================================================
SERVER_LIST_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" crossorigin="anonymous">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PANELVEEX — Servers</title>
<style>
:root{--bg:#202020;--text:#f0eef2;--green:#1eb889;--red:#bf3941}
*{box-sizing:border-box;margin:0;padding:0;font-family:Inter,"Segoe UI",Tahoma,sans-serif}
html,body{min-height:100%;background:var(--bg);color:var(--text)}
body{font-size:13px}.server-shell{min-height:100vh}
.topbar{height:44px;background:#121116;border-top:2px solid #29262e;border-bottom:1px solid #25222a;display:flex;align-items:center;justify-content:space-between;padding:0 28px;position:sticky;top:0;z-index:20}
.brand{font-size:16px;font-weight:800;letter-spacing:.2px;color:#f0eef2;display:flex;align-items:center;gap:6px}.brand i{font-size:12px;color:#a6a0ad}.brand .accent{color:#fff}
.top-actions{display:flex;align-items:center;gap:28px}.top-actions button{background:none;border:0;color:#e8e5ea;font-size:14px;cursor:pointer;opacity:.9}.top-actions button:hover{color:#fff;opacity:1}.top-actions .active{color:#fff}.avatar{width:23px;height:23px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:#f5b91b;color:#191719;font-size:12px;box-shadow:0 0 0 1px #f5b91b}
.server-main{max-width:900px;margin:30px auto 0;padding:0 10px}.server-toolbar{display:flex;justify-content:flex-end;align-items:center;gap:8px;color:#75727a;font-size:9px;text-transform:uppercase;margin:0 2px 6px}.switch{width:36px;height:19px;background:#3887ee;border-radius:10px;display:inline-flex;align-items:center;padding:2px;box-shadow:0 0 0 1px #5a9cf6}.switch span{width:15px;height:15px;border-radius:50%;background:#f7f9ff;margin-left:auto;box-shadow:0 1px 3px #111}
.server-list{display:flex;flex-direction:column;gap:4px}.server-card{position:relative;min-height:78px;background:#333;border:1px solid #101015;border-radius:2px;display:grid;grid-template-columns:48px minmax(220px,1fr) 132px 98px 98px 10px;align-items:center;gap:7px;padding:10px 0 10px 10px;overflow:hidden;cursor:pointer;transition:background .18s,transform .18s}.server-card:hover{background:#1b1920;transform:translateX(2px)}.server-icon{width:62px;height:39px;border-radius:24px;display:flex;align-items:center;justify-content:center;background:#707070;color:#e8e8e8;font-size:16px}.server-name{font-size:14px;color:#eeeaf0;margin-bottom:4px}.server-type{font-size:10px;color:#a4a0a9}.server-address,.metric{font-size:10px;color:#aca8b0;white-space:nowrap}.server-address i,.metric i{font-size:11px;color:#8f8a94;margin-right:5px}.metric small{display:block;color:#67636b;font-size:8px;margin-top:3px}.server-bar{height:58px;border-radius:8px 0 0 8px;background:var(--red)}.server-bar.offline{background:var(--red)}.footer{text-align:center;color:#706d73;font-size:10px;margin:29px 0 20px}.empty-server-state{min-height:260px;background:#111015;border:1px solid #29262e;border-radius:3px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:#77727b}.empty-server-state i{font-size:34px;color:#5d5962}.empty-server-state strong{font-size:18px;color:#d8d4db;font-weight:500}.empty-server-state span{font-size:12px;color:#77727b}.empty-server-state{min-height:260px;background:#111015;border:1px solid #29262e;border-radius:3px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:#77727b}.empty-server-state i{font-size:34px;color:#5d5962}.empty-server-state strong{font-size:18px;color:#d8d4db;font-weight:500}.empty-server-state span{font-size:12px;color:#77727b}
@media(max-width:760px){.topbar{padding:0 18px}.top-actions{gap:20px}.server-main{margin-top:28px;padding:0 8px}.server-card{grid-template-columns:70px minmax(150px,1fr) 106px 88px 88px 8px;gap:5px;padding-left:8px}.server-icon{width:62px;height:39px}.server-name{font-size:12px}.server-type,.server-address,.metric{font-size:9px}.metric small{font-size:7px}}
@media(max-width:560px){.server-main{margin-top:20px}.topbar{height:46px}.brand{font-size:14px}.top-actions{gap:16px}.server-card{grid-template-columns:70px minmax(0,1fr) 74px 8px;min-height:62px}.server-card .server-address,.server-card .metric:nth-of-type(2),.server-card .metric:nth-of-type(3){display:none}.server-icon{width:62px;height:39px}.server-name{font-size:12px}.server-type{font-size:9px}.server-bar{height:46px}.footer{margin-top:26px}}
/* nnn reference states */
.btn-power{display:inline-flex;align-items:center;justify-content:center;gap:8px;text-transform:uppercase;letter-spacing:1px;min-height:58px;border-radius:0;font-weight:700}
.btn-power:disabled{opacity:.38;cursor:not-allowed;filter:saturate(.45)}
.btn-start{background:#527ab5}.btn-restart{background:#343236}.btn-stop{background:#e52328}
.console-box{background:#050505;color:#f3f3f3;font-family:Consolas,Monaco,monospace;font-size:13px;line-height:1.45}
.file-row{background:#101010;border-color:#292929;border-radius:0;min-height:44px;padding:8px 12px}.file-row .menu{color:#fff;font-size:17px}.file-row .ico{color:#bcbcbc}.file-row .name{font-size:14px}
.file-row.selected{background:#343434!important}.btn-clear-selection{background:#4a3c3c!important}.btn-clear-selection:hover{background:#694949!important}.file-action-menu{position:fixed;z-index:3000;width:186px;background:#111;border:1px solid #3a3a3a;box-shadow:0 10px 28px #000b;padding:7px 0;color:#eee}
.file-action-menu button{width:100%;display:flex;align-items:center;gap:14px;border:0;background:none;color:#eee;padding:12px 16px;text-align:left;font-size:15px;cursor:pointer}.file-action-menu button:hover{background:#303030}.file-action-menu i{width:18px;color:#bcbcbc;font-size:14px}.file-row.menu-open{background:#343434!important}
.server-main{max-width:900px;margin:26px auto 0}.server-list{gap:8px}.server-card{min-height:88px;background:#242327;border:1px solid #2f2d32;border-radius:4px;grid-template-columns:70px minmax(0,1fr) 108px 90px 90px;padding:12px 0 12px 12px}.server-icon{width:58px;height:38px;background:#777;border-radius:22px}.server-bar{display:none!important}.server-card.online .server-bar{background:#23b879}.server-name{font-size:15px;font-weight:600}.server-type{color:#938f97}.server-address,.metric{color:#aba7ad}
@media(max-width:560px){.server-card{grid-template-columns:56px minmax(0,1fr);min-height:70px;padding-left:10px}.server-icon{width:48px;height:34px}.server-card .server-address,.server-card .metric{display:none}.server-bar{height:52px}.server-name{font-size:14px}}
</style>
</head>
<body>
<div class="server-shell">
  <header class="topbar">
    <div class="brand"><i>◁</i> <span class="accent">PANELVEEX</span> <i>▷</i></div>
    <div class="top-actions">
      <button title="Search" onclick="document.getElementById('server-search').focus()"><i class="fas fa-search"></i></button>
      <button class="active" title="Servers"><i class="fas fa-layer-group"></i></button>
      <button title="Settings" onclick="location.href='/server/primary#settings'"><i class="fas fa-cog"></i></button>
      <span class="avatar" title="Account"><i class="fas fa-face-smile"></i></span>
      <button title="Logout" onclick="location.href='/logout'"><i class="fas fa-right-from-bracket"></i></button>
    </div>
  </header>
  <main class="server-main">
    <input id="server-search" aria-label="Search servers" placeholder="" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0">
    <div class="server-list" id="server-list">__SERVER_CARDS__</div>
    <div class="footer">♘ king panelveex © 2015 - 2026</div>
  </main>
</div>
</body>
</html>
'''

def _server_card_html(server):
    name = html.escape(str(server.get('name', 'Python Server')))
    kind = html.escape(str(server.get('type', 'Python Application Server')))
    address = html.escape(str(server.get('address', '127.0.0.1:25567')))
    sid = html.escape(str(server.get('id', 'primary')), quote=True)
    cpu = html.escape(str(server.get('cpu', '0.00 %')))
    memory = html.escape(str(server.get('memory', '0 Bytes')))
    disk = html.escape(str(server.get('disk', '0 Bytes')))
    status = 'offline' if server.get('status') == 'offline' else 'online'
    return f'''\n      <article class="server-card {status}" onclick="location.href='/server/{sid}'" tabindex="0" onkeydown="if(event.key==='Enter')location.href='/server/{sid}'">\n        <div class="server-icon"><i class="fas fa-server"></i></div>\n        <div><div class="server-name">{name}</div><div class="server-type">{kind}</div></div>\n        <div class="server-address"><i class="fas fa-network-wired"></i>{address}</div>\n        <div class="metric"><i class="fas fa-microchip"></i>{cpu}<small>of 100%</small></div>\n        <div class="metric"><i class="fas fa-hard-drive"></i>{memory}<small>{disk}</small></div>\n      </article>'''

def get_server_catalog(username):
    stats = get_system_stats()
    host = stats.get('public_ip') or stats.get('hostname') or '127.0.0.1'
    port = MASTER_CONFIG.get('port', 20048)
    users = load_users()
    servers = []
    if username == MASTER_USERNAME:
        servers.append({'id': 'primary', 'name': 'NodeJS Server', 'type': 'Node.js Application Server', 'address': f'{host}:{port}', 'cpu': '0.00 %', 'memory': '0 Bytes', 'disk': '288.28 MiB'})
        for uname, data in list(users.items())[:8]:
            if not isinstance(data, dict):
                continue
            runtime = data.get('runtime', 'python')
            label = data.get('server_name', '').strip()
            if not label:
                continue
            servers.append({'id': 'user-' + re.sub(r'[^a-zA-Z0-9_-]', '-', uname), 'name': label, 'type': 'Node.js Application Server' if runtime == 'nodejs' else 'Python Application Server', 'address': f'{host}:{port}', 'cpu': '0.00 %', 'memory': '0 Bytes', 'disk': '0 Bytes'})
    else:
        data = users.get(username, {}) if isinstance(users, dict) else {}
        runtime = data.get('runtime', 'python') if isinstance(data, dict) else 'python'
        label = data.get('server_name', '').strip()
        count = max(1, min(int(data.get('max_servers', 1)) if isinstance(data, dict) else 1, 8))
        if not label:
            return []
        if not label:
            return []
        for idx in range(count):
            suffix = '' if idx == 0 else f' {idx + 1}'
            servers.append({'id': 'primary' if idx == 0 else f'primary-{idx + 1}', 'name': label + suffix, 'type': 'Node.js Application Server' if runtime == 'nodejs' else 'Python Application Server', 'address': f'{host}:{port + idx}', 'cpu': '0.00 %', 'memory': '0 Bytes', 'disk': '0 Bytes'})
    return servers

def get_server_list_html(username):
    catalog = get_server_catalog(username)
    cards_html = ''.join(_server_card_html(s) for s in catalog)
    if not cards_html:
        cards_html = '<div class="empty-server-state"><i class="fas fa-server"></i><strong>No server available</strong><span>Ask the Admin to create a server for your account.</span></div>'
    return SERVER_LIST_TEMPLATE.replace('__SERVER_CARDS__', cards_html)

def get_html_template(is_master, username=None, server=None):
    server = server or {}
    server_name = html.escape(str(server.get('name', 'Python Server')))
    server_type = html.escape(str(server.get('type', 'Python Application Server')))
    server_address = html.escape(str(server.get('address', '127.0.0.1:25567')))
    master_tabs = ''
    if is_master:
        master_tabs = '''
        <div class="tab-item" data-tab="users">Users</div>
        <div class="tab-item" data-tab="backups">Backups</div>
        <div class="tab-item" data-tab="network">Network</div>
        <div class="tab-item" data-tab="startup">Startup</div>
        <div class="tab-item" data-tab="settings">Settings</div>
        <div class="tab-item" data-tab="activity">Activity</div>
        <div class="tab-item" data-tab="owner" style="color:#f6b73c;font-weight:700">&#128081; Owner</div>
        '''
    else:
        master_tabs = '''
        <div class="tab-item" data-tab="settings">Settings</div>
        <div class="tab-item" data-tab="activity">Activity</div>
        '''

    return r'''
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" crossorigin="anonymous">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PANELVEEX — Server Panel</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter','Segoe UI',Tahoma,sans-serif}
html,body{background:#1f2933;color:#d6dde3;min-height:100vh}

/* ============== HEADER ============== */
.topbar{
  background:#1a242c;
  border-bottom:1px solid #2a3640;
  padding:14px 20px;
  display:flex;align-items:center;justify-content:space-between;
}
.topbar .brand{font-size:18px;font-weight:600;color:#fff}
.topbar .brand .lc{color:#29c7d3}
.topbar .icons{display:flex;gap:18px;align-items:center}
.topbar .icons .ic{
  color:#9aa9b3;font-size:18px;cursor:pointer;
  background:none;border:0;
}
.topbar .icons .ic:hover{color:#fff}
.topbar .avatar{
  width:28px;height:28px;border-radius:50%;
  background:linear-gradient(135deg,#f6b73c,#65c466);
  display:inline-block;
}

/* ============== TABS ============== */
.tabs{
  background:#1f2933;
  border-bottom:1px solid #2a3640;
  display:flex;
  overflow-x:auto;
  padding:0 10px;
  scrollbar-width:thin;
}
.tabs::-webkit-scrollbar{height:3px}
.tabs::-webkit-scrollbar-thumb{background:#3a4a55;border-radius:3px}
.tab-item{
  padding:14px 18px;
  color:#9aa9b3;
  cursor:pointer;
  font-size:14px;
  white-space:nowrap;
  border-bottom:2px solid transparent;
  transition:.2s;
  user-select:none;
}
.tab-item:hover{color:#fff}
.tab-item.active{color:#29c7d3;border-bottom-color:#29c7d3}

/* ============== CONTENT ============== */
.container{
  max-width:1100px;
  margin:0 auto;
  padding:18px;
}
.tab-content{display:none;animation:fadein .25s}
.tab-content.active{display:block}
@keyframes fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}

/* ============== CONSOLE ============== */
.power-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px}
.btn-power{
  padding:12px;border:0;border-radius:4px;font-weight:600;font-size:14px;cursor:pointer;
  color:#fff;transition:.2s;
}
.btn-start{background:#2f6fed}
.btn-start:hover{background:#1d5cd8}
.btn-restart{background:#5a6c78}
.btn-restart:hover{background:#4a5b66}
.btn-stop{background:#e53935}
.btn-stop:hover{background:#c62828}

.console-box{
  background:#0d1419;
  border:1px solid #2a3640;
  border-radius:4px;
  padding:14px;
  font-family:'Consolas','Monaco',monospace;
  font-size:12px;
  color:#c8d4dc;
  height:340px;
  overflow-y:auto;
  white-space:pre-wrap;
  word-break:break-all;
  margin-bottom:10px;
}
.console-box::-webkit-scrollbar{width:6px}
.console-box::-webkit-scrollbar-thumb{background:#3a4a55;border-radius:3px}
.console-box .console-line{display:block;white-space:pre-wrap}.console-box .console-prefix{color:#f2c879;font-weight:700}.console-box .console-output{color:#f2f2f2}

.cmd-input{
  display:flex;align-items:center;
  background:#1a242c;
  border:1px solid #2a3640;
  border-radius:4px;
  padding:0 12px;margin-bottom:14px;
}
.cmd-input .prompt{color:#29c7d3;margin-right:8px;font-weight:700}
.cmd-input input{
  flex:1;background:none;border:0;outline:0;color:#d6dde3;
  padding:11px 0;font-family:monospace;font-size:13px;
}

/* ============== STATS GRID ============== */
.stats-grid{
  display:grid;grid-template-columns:1fr 1fr;gap:8px;
}
.stat-card{
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-left:3px solid #29c7d3;
  border-radius:4px;
  padding:10px 12px;
}
.stat-card.alt{border-left-color:#f6b73c}
.stat-card.alt2{border-left-color:#65c466}
.stat-card.alt3{border-left-color:#e53935}
.stat-card .lbl{font-size:11px;color:#9aa9b3;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px}
.stat-card .val{font-size:14px;color:#fff;font-weight:600}
.stat-card .val .max{color:#7a8c98;font-weight:400;font-size:12px}

/* ============== FILES ============== */
.action-buttons{display:flex;flex-direction:column;gap:8px;margin-bottom:14px}
.btn-bar{
  width:100%;padding:13px;border:0;border-radius:4px;cursor:pointer;
  font-size:14px;font-weight:600;color:#fff;transition:.2s;
}
.btn-create-dir{background:#5a6c78}
.btn-create-dir:hover{background:#4a5b66}
.btn-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.btn-upload,.btn-newfile{background:#2f6fed}
.btn-upload:hover,.btn-newfile:hover{background:#1d5cd8}

.breadcrumb{
  padding:8px 4px;color:#9aa9b3;font-size:13px;margin-bottom:8px;
  display:flex;align-items:center;gap:6px;flex-wrap:wrap;
}
.breadcrumb .crumb{color:#29c7d3;cursor:pointer}
.breadcrumb .crumb:hover{text-decoration:underline}
.breadcrumb .sep{color:#5a6c78}

.file-list{background:transparent}
.file-row{
  display:flex;align-items:center;gap:10px;
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-radius:4px;
  padding:10px 12px;
  margin-bottom:4px;
  cursor:pointer;
  transition:.15s;
}
.file-row:hover{background:#324250}
.file-row .chk{width:14px;height:14px;border:1px solid #5a6c78;border-radius:2px;flex-shrink:0}
.file-row .ico{font-size:18px;flex-shrink:0;color:#9aa9b3}
.file-row .name{flex:1;color:#d6dde3;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.file-row .menu{
  color:#9aa9b3;cursor:pointer;padding:4px 8px;font-size:18px;
  border-radius:3px;
}
.file-row .menu:hover{background:#3a4a55;color:#fff}
/* ── File action buttons ── */
.fa-btns{display:flex;gap:5px;flex-shrink:0;opacity:0;transition:opacity .18s}
.file-row:hover .fa-btns{opacity:1}
.fab{width:30px;height:30px;border:0;border-radius:7px;cursor:pointer;font-size:12px;
  display:inline-flex;align-items:center;justify-content:center;
  transition:transform .15s,box-shadow .15s;position:relative;flex-shrink:0}
.fab::after{content:attr(title);position:absolute;bottom:calc(100% + 5px);left:50%;
  transform:translateX(-50%);background:#0d1a22;color:#d6dde3;font-size:10px;
  padding:3px 7px;border-radius:4px;white-space:nowrap;pointer-events:none;
  opacity:0;transition:opacity .12s;z-index:99}
.fab:hover::after{opacity:1}
.fab:hover{transform:translateY(-2px);box-shadow:0 4px 10px rgba(0,0,0,.35)}
.fab:active{transform:translateY(0)}
.fab-run {background:linear-gradient(135deg,#2ecc71,#27ae60);color:#fff}
.fab-edit{background:linear-gradient(135deg,#3498db,#2980b9);color:#fff}
.fab-ren {background:linear-gradient(135deg,#f39c12,#e67e22);color:#fff}
.fab-del {background:linear-gradient(135deg,#e74c3c,#c0392b);color:#fff}

/* ============== SECTION CARDS ============== */
.section-card{
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-radius:4px;
  margin-bottom:14px;
  overflow:hidden;
}
.section-head{
  padding:12px 16px;
  border-bottom:1px solid #3a4a55;
  font-size:12px;color:#9aa9b3;text-transform:uppercase;letter-spacing:1px;font-weight:600;
}
.section-body{padding:16px}
.field-block{margin-bottom:14px}
.field-block:last-child{margin-bottom:0}
.field-block label{display:block;color:#9aa9b3;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.field-block input,.field-block textarea,.field-block select{
  width:100%;padding:10px 12px;
  background:#1f2933;
  border:1px solid #3a4a55;
  border-radius:4px;color:#fff;font-size:13px;outline:none;
  font-family:inherit;
}
.field-block input:focus,.field-block textarea:focus{border-color:#29c7d3}
.field-block textarea{min-height:80px;resize:vertical}

.btn-action{
  padding:10px 22px;border:0;border-radius:4px;cursor:pointer;
  background:#2f6fed;color:#fff;font-weight:600;font-size:13px;
}
.btn-action:hover{background:#1d5cd8}
.btn-action.danger{background:#e53935}
.btn-action.danger:hover{background:#c62828}
.btn-action.gray{background:#5a6c78}
.btn-action.gray:hover{background:#4a5b66}

.row-end{display:flex;justify-content:flex-end;margin-top:8px}

/* ============== ACTIVITY FEED ============== */
.activity-card{
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-radius:4px;
  padding:12px 16px;
  margin-bottom:6px;
}
.activity-card .a-head{
  color:#fff;font-size:14px;margin-bottom:4px;
}
.activity-card .a-head .user{color:#29c7d3;font-weight:600}
.activity-card .a-head .action{color:#fff;font-weight:500}
.activity-card .a-desc{color:#9aa9b3;font-size:13px;margin-bottom:4px}
.activity-card .a-desc code{background:#1a242c;padding:1px 6px;border-radius:3px;color:#f6b73c}
.activity-card .a-meta{color:#7a8c98;font-size:12px}

/* ============== NETWORK / PORTS ============== */
.port-card{
  background:#2b3a43;
  border:1px solid #3a4a55;
  border-radius:4px;padding:14px;margin-bottom:8px;
}
.port-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.port-host{
  background:#1a242c;border-radius:3px;padding:4px 10px;color:#fff;font-size:13px;
  font-family:monospace;
}
.port-badge{
  background:#1a242c;border-radius:3px;padding:4px 10px;color:#fff;font-size:13px;font-weight:600;
}
.port-note{color:#7a8c98;font-size:12px;margin-top:4px}

/* ============== USER LIST ============== */
.user-row{
  display:flex;justify-content:space-between;align-items:center;
  background:#2b3a43;border:1px solid #3a4a55;border-radius:4px;
  padding:10px 14px;margin-bottom:6px;
}
.user-row .uname{color:#fff;font-weight:500}
.user-row .meta{color:#7a8c98;font-size:12px}

/* ============== MODAL ============== */
.modal{
  position:fixed;inset:0;background:rgba(0,0,0,.7);
  display:none;align-items:center;justify-content:center;z-index:1000;padding:14px;
}
.modal.show{display:flex}
.modal-box{
  background:#2b3a43;border:1px solid #3a4a55;border-radius:6px;
  width:min(560px,100%);max-height:90vh;overflow-y:auto;
}
.modal-head{padding:14px 18px;border-bottom:1px solid #3a4a55;display:flex;justify-content:space-between;align-items:center}
.modal-head h3{color:#fff;font-size:16px;font-weight:600}
.modal-head .close{background:none;border:0;color:#9aa9b3;font-size:24px;cursor:pointer;line-height:1}
.modal-body{padding:18px}
.modal-foot{padding:12px 18px;border-top:1px solid #3a4a55;display:flex;justify-content:flex-end;gap:8px}

.editor-textarea{
  width:100%;min-height:55vh;
  background:#0d1419;border:1px solid #3a4a55;border-radius:4px;
  color:#c8d4dc;font-family:monospace;font-size:13px;padding:12px;outline:none;
  resize:vertical;
}

.toast{
  position:fixed;bottom:16px;right:16px;
  background:#2b3a43;border:1px solid #29c7d3;
  color:#fff;padding:10px 16px;border-radius:4px;font-size:13px;
  box-shadow:0 6px 20px rgba(0,0,0,.5);z-index:2000;
  animation:tin .3s;
}
.toast.error{border-color:#e53935}
@keyframes tin{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}

.foot-pterod{text-align:center;color:#5a6c78;font-size:11px;padding:18px 0}

/* ============== OWNER PANEL ============== */
@keyframes ownerGlowPulse{0%,100%{opacity:.55}50%{opacity:1}}
@keyframes ownerFloatIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
#tab-owner{animation:ownerFloatIn .35s ease}
.owner-hero{
  position:relative;overflow:hidden;
  background:
    radial-gradient(ellipse 120% 140% at 50% -20%,#f6b73c1c 0%,transparent 60%),
    linear-gradient(135deg,#161e25 0%,#232f38 55%,#1a242c 100%);
  border:1px solid #f6b73c3d;
  border-radius:12px;
  padding:26px 20px;
  margin-bottom:16px;
  text-align:center;
  box-shadow:0 8px 24px -12px #000000aa, inset 0 1px 0 #ffffff08;
}
.owner-hero:before{
  content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(90deg,transparent,#f6b73c,transparent);
  height:2px;top:0;opacity:.7;animation:ownerGlowPulse 3s ease-in-out infinite;
}
.owner-hero h2{
  color:#ffd479;font-size:21px;margin-bottom:6px;font-weight:800;letter-spacing:.3px;
  text-shadow:0 0 18px #f6b73c4d;
  display:flex;align-items:center;justify-content:center;gap:10px;
}
.owner-hero h2 i{
  display:inline-flex;align-items:center;justify-content:center;
  width:34px;height:34px;border-radius:50%;font-size:15px;
  background:radial-gradient(circle at 35% 30%,#ffe4a3,#f6b73c 60%,#c98f1f);
  color:#1a242c;box-shadow:0 0 0 4px #f6b73c1a,0 4px 14px -4px #f6b73c99;
}
.owner-hero p{color:#9fb0ba;font-size:13px;letter-spacing:.2px}
.owner-stats-grid{
  display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px;
}
@media(max-width:600px){.owner-stats-grid{grid-template-columns:1fr 1fr}}
.owner-stat{
  --acc:#f6b73c;
  position:relative;
  background:linear-gradient(160deg,#2b3a43 0%,#242f37 100%);
  border:1px solid #3a4a55;
  border-top:3px solid var(--acc);
  border-radius:8px;padding:15px 10px;text-align:center;
  transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease;
}
.owner-stat:hover{
  transform:translateY(-3px);
  border-color:var(--acc);
  box-shadow:0 10px 20px -10px color-mix(in srgb, var(--acc) 70%, transparent);
}
.owner-stat .o-num{font-size:26px;font-weight:800;color:var(--acc);text-shadow:0 0 16px color-mix(in srgb, var(--acc) 45%, transparent);line-height:1.15}
.owner-stat .o-lbl{font-size:10.5px;color:#9aa9b3;text-transform:uppercase;letter-spacing:.6px;margin-top:5px}
#ow-stats-grid .owner-stat:nth-child(1){--acc:#29c7d3}
#ow-stats-grid .owner-stat:nth-child(2){--acc:#2ecc71}
#ow-stats-grid .owner-stat:nth-child(3){--acc:#e53935}
#ow-stats-grid .owner-stat:nth-child(4){--acc:#5b8def}
#ow-stats-grid .owner-stat:nth-child(5){--acc:#f6b73c}
#ow-stats-grid .owner-stat:nth-child(6){--acc:#b07cf0}

/* Owner-scoped elevation for shared section/button/field styles -- does not touch other tabs */
#tab-owner .section-card{
  border-radius:8px;
  border-color:#3a4a55;
  background:linear-gradient(160deg,#2b3a43 0%,#263139 100%);
  box-shadow:0 6px 18px -12px #000000cc;
  transition:border-color .2s ease;
}
#tab-owner .section-card:hover{border-color:#4a5b66}
#tab-owner .section-head{
  display:flex;align-items:center;gap:8px;
  border-bottom:1px solid #3a4a55;
  background:linear-gradient(180deg,#f6b73c0d,transparent);
  position:relative;
}
#tab-owner .section-head:before{
  content:"";width:3px;align-self:stretch;margin:-12px 4px -12px -16px;
  background:linear-gradient(#f6b73c,#f6b73c66);border-radius:0 2px 2px 0;
}
#tab-owner .section-card[style*="e5393544"] .section-head:before{background:linear-gradient(#e53935,#e5393566)}
#tab-owner .btn-action{
  letter-spacing:.2px;
  transition:transform .15s ease,box-shadow .15s ease,background .15s ease;
}
#tab-owner .btn-action:hover{transform:translateY(-1px);box-shadow:0 6px 14px -6px #2f6fed88}
#tab-owner .btn-action.danger:hover{box-shadow:0 6px 14px -6px #e5393588}
#tab-owner .btn-action.gray:hover{box-shadow:0 6px 14px -6px #00000055}
#tab-owner .field-block input:focus,#tab-owner .field-block textarea:focus{
  border-color:#f6b73c;box-shadow:0 0 0 3px #f6b73c22;
}
.maint-toggle{
  display:flex;align-items:center;justify-content:space-between;
  background:linear-gradient(160deg,#2b3a43,#242f37);border:1px solid #3a4a55;border-radius:8px;
  padding:15px 18px;margin-bottom:8px;
}
.maint-toggle .mt-label{color:#fff;font-size:14px;font-weight:600}
.maint-toggle .mt-sub{color:#9aa9b3;font-size:12px;margin-top:2px}
.toggle-switch{position:relative;width:50px;height:26px;flex-shrink:0}
.toggle-switch input{opacity:0;width:0;height:0}
.toggle-slider{
  position:absolute;cursor:pointer;inset:0;
  background:#3a4a55;border-radius:26px;transition:.3s;
  box-shadow:inset 0 1px 3px #00000055;
}
.toggle-slider:before{
  position:absolute;content:"";height:20px;width:20px;
  left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s;
  box-shadow:0 2px 4px #00000055;
}
.toggle-switch input:checked+.toggle-slider{background:#e53935;box-shadow:inset 0 1px 3px #00000055,0 0 10px #e5393566}
.toggle-switch input:checked+.toggle-slider:before{transform:translateX(24px)}
.bot-linked-badge{
  display:inline-flex;align-items:center;gap:6px;
  background:#1a242c;border:1px solid #65c46644;
  border-radius:20px;padding:4px 12px;
  font-size:12px;color:#65c466;
  box-shadow:0 0 12px -4px #65c46655;
}
.bot-unlinked-badge{
  display:inline-flex;align-items:center;gap:6px;
  background:#1a242c;border:1px solid #e5393544;
  border-radius:20px;padding:4px 12px;
  font-size:12px;color:#e53935;
}
.announce-card{
  background:linear-gradient(160deg,#2b3a43,#242f37);border:1px solid #3a4a55;border-left:3px solid #f6b73c;border-radius:6px;
  padding:12px 16px;margin-bottom:6px;
  display:flex;justify-content:space-between;align-items:center;
  transition:border-color .15s ease;
}
.announce-card:hover{border-color:#4a5b66;border-left-color:#f6b73c}
.announce-card .a-text{color:#d6dde3;font-size:13px;flex:1}
.announce-card .a-time{color:#7a8c98;font-size:11px;margin-left:10px;flex-shrink:0}
.zip-item{
  background:linear-gradient(160deg,#2b3a43,#242f37);border:1px solid #3a4a55;border-radius:6px;
  padding:10px 14px;margin-bottom:6px;
  display:flex;justify-content:space-between;align-items:center;
  transition:border-color .15s ease,transform .15s ease;
}
.zip-item:hover{border-color:#4a5b66;transform:translateX(2px)}
.zip-item .z-name{color:#d6dde3;font-size:13px;font-family:monospace}
.zip-item .z-size{color:#9aa9b3;font-size:11px}

/* ============== OWNER PANEL EXTRAS ============== */
.owner-section-title{
  display:flex;align-items:center;gap:8px;
  font-size:13px;font-weight:700;color:#f6b73c;
  letter-spacing:.6px;text-transform:uppercase;
  margin-bottom:12px;border-bottom:1px solid #f6b73c22;padding-bottom:8px;
}
.owner-user-table{width:100%;border-collapse:collapse;font-size:12px}
.owner-user-table th{
  color:#9aa9b3;font-weight:600;text-align:left;
  padding:8px 10px;border-bottom:1px solid #2a3640;
  text-transform:uppercase;letter-spacing:.4px;font-size:11px;
}
.owner-user-table td{
  padding:10px;border-bottom:1px solid #1e2b33;
  vertical-align:middle;
}
.owner-user-table tr:last-child td{border-bottom:none}
.owner-user-table tr:hover td{background:#f6b73c0d}
.u-badge{
  display:inline-flex;align-items:center;gap:5px;padding:2px 9px;border-radius:10px;
  font-size:10px;font-weight:700;letter-spacing:.3px;
}
.u-badge:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex-shrink:0}
.u-badge.online{background:#2ecc7122;color:#2ecc71;border:1px solid #2ecc7144}
.u-badge.offline{background:#3a4a5566;color:#7a8c98;border:1px solid #3a4a55}
.u-badge.banned{background:#e5393522;color:#e53935;border:1px solid #e5393544}
.owner-action-btn{
  border:none;border-radius:5px;padding:5px 11px;
  font-size:11px;cursor:pointer;font-weight:600;transition:.15s ease;
}
.owner-action-btn:hover{transform:translateY(-1px)}
.owner-action-btn.ban{background:#e5393522;color:#e53935;border:1px solid #e5393533}
.owner-action-btn.ban:hover{background:#e53935;color:#fff;box-shadow:0 4px 10px -4px #e5393599}
.owner-action-btn.unban{background:#2ecc7122;color:#2ecc71;border:1px solid #2ecc7133}
.owner-action-btn.unban:hover{background:#2ecc71;color:#111;box-shadow:0 4px 10px -4px #2ecc7199}
.owner-action-btn.del{background:#1a242c;color:#9aa9b3;border:1px solid #2a3640}
.owner-action-btn.del:hover{background:#e53935;color:#fff;border-color:#e53935;box-shadow:0 4px 10px -4px #e5393599}
.owner-action-btn.pw{background:#1a242c;color:#9aa9b3;border:1px solid #2a3640}
.owner-action-btn.pw:hover{background:#f6b73c;color:#111;border-color:#f6b73c;box-shadow:0 4px 10px -4px #f6b73c99}
.session-row{
  display:flex;align-items:center;justify-content:space-between;
  background:#1e2b33;border:1px solid #2a3640;border-radius:8px;
  padding:11px 14px;margin-bottom:6px;
  transition:border-color .15s ease;
}
.session-row:hover{border-color:#2ecc7166}
.session-row .s-user{font-weight:600;color:#29c7d3;font-size:13px;display:flex;align-items:center;gap:7px}
.session-row .s-user:before{content:"";width:7px;height:7px;border-radius:50%;background:#2ecc71;box-shadow:0 0 8px #2ecc71aa;flex-shrink:0}
.session-row .s-meta{color:#9aa9b3;font-size:11px;margin-top:2px}
.feed-item{
  display:flex;gap:10px;align-items:flex-start;
  background:#1e2b33;border:1px solid #2a3640;border-radius:8px;
  padding:11px 14px;margin-bottom:6px;
  transition:border-color .15s ease,transform .15s ease;
}
.feed-item:hover{border-color:#3a4a55;transform:translateX(2px)}
.feed-item .feed-icon{
  width:30px;height:30px;border-radius:50%;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;font-size:12px;
  box-shadow:inset 0 0 0 1px #ffffff14;
}
.feed-item .feed-icon.auth{background:#2ecc7122;color:#2ecc71}
.feed-item .feed-icon.owner{background:#f6b73c22;color:#f6b73c}
.feed-item .feed-icon.user{background:#29c7d322;color:#29c7d3}
.feed-item .feed-icon.other{background:#3a4a55;color:#9aa9b3}
.feed-item .feed-body{flex:1}
.feed-item .feed-action{font-size:12px;color:#c8d4dc;font-weight:600}
.feed-item .feed-detail{font-size:11px;color:#7a8c98;margin-top:2px}
.feed-item .feed-time{font-size:10px;color:#4a5a65;margin-top:3px}
.creds-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:540px){.creds-grid{grid-template-columns:1fr}}
#tab-owner #bot-console{
  border-color:#2a3640;
  background:radial-gradient(ellipse at top left,#0f1a20,#0d1419 70%);
  box-shadow:inset 0 0 20px -8px #29c7d340;
}

/* ============== RESPONSIVE ============== */
@media (max-width:520px){
  .stats-grid{grid-template-columns:1fr 1fr}
  .topbar .brand{font-size:15px}
  .container{padding:12px}
}

/* final reference alignment */
.btn-power{min-height:58px;border-radius:0;text-transform:uppercase;letter-spacing:1px;font-weight:700}.btn-power:disabled{opacity:.38;cursor:not-allowed;filter:saturate(.45)}
/* final reference alignment */
.btn-power{min-height:58px;border-radius:0;text-transform:uppercase;letter-spacing:1px;font-weight:700}.btn-power:disabled{opacity:.38;cursor:not-allowed;filter:saturate(.45)}
/* ============== PANELVEEX REFERENCE MATCH ============== */
.console-box{background:#050505!important;color:#fff!important;font-family:Consolas,Monaco,monospace!important;font-size:17px!important;font-weight:500;line-height:1.28;border:0!important;border-radius:0!important;box-shadow:none!important;width:100%;min-height:520px;margin:0!important;padding:14px 10px}.console-box .console-line,.console-box .console-output{color:#fff;font-size:17px!important}.console-box .console-prefix{color:#f2c879;font-weight:700}
.console-box .console-line{display:block;margin:0!important;padding:0!important;height:auto;line-height:1.28!important;white-space:pre-wrap;word-break:normal;overflow-wrap:normal;letter-spacing:0}.console-box br{line-height:1.28}
.file-tools-row{display:flex;gap:8px}.btn-select,.btn-archive{background:#343236!important}.btn-select:hover,.btn-archive:hover{background:#4a474d!important}.file-row .chk{cursor:pointer}.file-row.selected .chk{background:#527ab5;border-color:#527ab5;box-shadow:inset 0 0 0 3px #211f27}
.file-row.selected{background:#343434!important}.file-action-menu{position:fixed;z-index:3000;width:186px;background:#111;border:1px solid #3a3a3a;box-shadow:0 10px 28px #000b;padding:7px 0;color:#eee}.file-action-menu button{width:100%;display:flex;align-items:center;gap:14px;border:0;background:none;color:#eee;padding:12px 16px;text-align:left;font-size:15px;cursor:pointer}.file-action-menu button:hover{background:#303030}.file-action-menu i{width:18px;color:#bcbcbc;font-size:14px}.file-row.menu-open{background:#343434!important}
:root{--dravex-bg:#141316;--dravex-panel:#1b1920;--dravex-card:#211f27;--dravex-line:#2b2830;--dravex-muted:#8e8993;--dravex-teal:#1fc5d6}
html,body{background:var(--dravex-bg);color:#eeeaf0}
.topbar{height:62px;background:#141316;border-bottom:1px solid #242129;padding:0 38px;position:fixed;top:0;left:0;right:0;z-index:100}
.topbar .brand{font-size:22px;letter-spacing:.4px;display:flex;align-items:center;gap:7px}.topbar .brand i{font-size:14px;color:#a29ca8}.topbar .brand .lc{color:#f5f2f6}
.topbar .icons{gap:28px}.topbar .icons .ic{color:#eeebef;font-size:16px}.topbar .avatar{width:23px;height:23px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:#f5b91b;color:#191719;font-size:12px;box-shadow:0 0 0 1px #f5b91b}.topbar .avatar i{font-size:12px;color:#191719}
.tabs{position:fixed;top:62px;left:0;bottom:0;width:220px;background:#17151a;border:0;border-right:1px solid #26232a;padding:27px 10px;display:flex;flex-direction:column;overflow-y:auto;overflow-x:hidden;z-index:90;gap:10px}.tab-item{width:100%;min-height:48px;padding:0 16px;color:#c7c3ca;border:0;border-radius:6px;display:flex;align-items:center;font-size:14px;background:transparent}.tab-item:before{font-family:"Font Awesome 6 Free";font-weight:900;width:28px;margin-right:8px;text-align:center;color:#8d8792;font-size:15px}.tab-item[data-tab="console"]:before{content:"\f120"}.tab-item[data-tab="files"]:before{content:"\f07b"}.tab-item[data-tab="databases"]:before{content:"\f1c0"}.tab-item[data-tab="schedules"]:before{content:"\f017"}.tab-item[data-tab="users"]:before{content:"\f0c0"}.tab-item[data-tab="backups"]:before{content:"\f1da"}.tab-item[data-tab="network"]:before{content:"\f1eb"}.tab-item[data-tab="startup"]:before{content:"\f04b"}.tab-item[data-tab="settings"]:before{content:"\f013"}.tab-item[data-tab="activity"]:before{content:"\f1da"}.tab-item[data-tab="owner"]:before{content:"\f521"}.tab-item:hover{background:#211f27;color:#fff}.tab-item.active{background:#ee2d21;color:#fff;border:0;box-shadow:0 8px 20px -12px #ee2d21}.tab-item.active:before{color:#fff}
.container{max-width:none;margin:0 0 0 220px;padding:92px 25px 20px;min-height:100vh}.tab-content{max-width:1090px;margin:0 auto}.tab-content.active{display:block}
#tab-console{display:none;grid-template-columns:minmax(0,1fr) 252px;gap:14px;align-items:start}#tab-console.active{display:grid}.server-header{grid-column:1 / -1;display:flex;justify-content:flex-end;align-items:flex-end;margin:8px 0 2px}.server-title{display:none!important}.server-title h1{font-size:23px;font-weight:700;color:#f5f2f6;line-height:1.2}.server-title p{font-size:14px;color:#aaa5ad;margin-top:4px}.server-address-badge{font-size:11px;color:#77727b;display:inline-block;margin-top:10px}.server-address-badge i{margin-right:5px;color:#938d99}.power-row{display:flex;gap:8px;margin:0;align-items:center}.btn-power{min-width:74px;padding:11px 18px;border-radius:4px;font-size:14px}.btn-start{background:#3678e7}.btn-restart{background:#838185}.btn-stop{background:#ed2b2b}.console-box{grid-column:1;grid-row:2 / span 3;background:#11151b;border:1px solid #252a32;border-radius:3px;height:510px;padding:14px;color:#c9c5cb;font-size:12px}.cmd-input{grid-column:1;grid-row:5;background:#1b1920;border:1px solid #292630}.mo-stats-header{grid-column:2;grid-row:2;margin:0 0 2px;align-self:start;padding:0 2px}.mo-stats-title{font-size:12px;color:#aaa5ad;text-transform:uppercase}.mo-refresh-btn{background:#1e1c23;border-color:#2c2932}.mo-grid{grid-column:2;grid-row:2;display:flex;flex-direction:column;gap:8px;margin-top:26px}.mo-card{background:#211f27;border:1px solid #2a2730;border-radius:2px;padding:12px 14px}.mo-card-icon{display:none}.mo-card-label{font-size:11px;color:#9b96a0}.mo-card-value{font-size:14px;color:#f4f0f5}.mo-bar-bg{height:3px}.mo-net-row{grid-column:2;grid-row:4;display:flex;flex-direction:column;gap:8px;margin-top:386px}.mo-net-item{background:#211f27;border:1px solid #2a2730;border-radius:2px;padding:12px}.mo-net-item .val{font-size:13px;color:#f4f0f5}.section-card{background:#1f1d24;border-color:#2b2831;border-radius:3px}.section-head{color:#aaa5ad;border-color:#2b2831}.file-row,.stat-card,.port-card,.user-row,.activity-card{background:#211f27;border-color:#2c2932}.file-row:hover{background:#28252e}.foot-pterod{color:#69646d}
#service-links-card{grid-column:1 / -1}.mo-stats-header{display:none}.toast{background:#211f27;border-color:var(--dravex-teal)}.vax-sidebar{position:fixed;top:62px;left:0;bottom:0;width:290px;background:#17151a;border-right:1px solid #2b2830;z-index:140;transform:translateX(-102%);transition:transform .22s ease;padding:18px 12px;box-shadow:12px 0 30px #0008}.vax-sidebar.open{transform:translateX(0)}.side-head{height:38px;color:#f6f3f7;display:flex;align-items:center;justify-content:space-between;padding:0 10px 12px;border-bottom:1px solid #2b2830;margin-bottom:12px}.side-head button{background:none;border:0;color:#aaa;font-size:28px;cursor:pointer}.side-items{display:flex;flex-direction:column;gap:7px}.vax-sidebar .tab-item{display:flex!important;width:100%!important;min-height:46px!important}.vax-sidebar-backdrop{position:fixed;inset:62px 0 0;background:#0009;z-index:130;display:none}.vax-sidebar-backdrop.open{display:block}.vax-charts{grid-column:1/-1;display:flex;flex-direction:column;gap:10px;margin-top:8px}.vax-chart{background:#111015;border:1px solid #232129;border-bottom:4px solid #29272e;border-radius:2px;padding:22px 30px 10px;position:relative;min-height:210px}.vax-chart h2{font-size:22px;font-weight:500;color:#f1edf2;margin:0 0 12px}.vax-chart h2 i{float:right;margin-left:14px;font-size:18px}.vax-chart .down{color:#f2c313}.vax-chart .up{color:#2bcbe4}.chart-grid{position:absolute;left:20px;top:64px;bottom:22px;width:98px;display:flex;flex-direction:column;justify-content:space-between;color:#c5c0c7;font-size:13px}.vax-chart svg{display:block;width:calc(100% - 105px);height:145px;margin-left:105px}.vax-chart .gridline{stroke:#454249;stroke-width:1;fill:none}.vax-chart polyline{fill:none;stroke:#2bcbe4;stroke-width:4;stroke-linejoin:round;stroke-linecap:round;stroke-dasharray:900;animation:vaxDash 7s linear infinite}.vax-chart polyline.cyan-line{stroke:#2bcbe4}.vax-chart polyline.yellow-line{stroke:#f3ba19}.vax-chart .yellow-line{animation-delay:-2s}@keyframes vaxDash{to{stroke-dashoffset:-900}}@media(max-width:800px){.vax-charts{grid-column:1}.vax-chart{min-height:210px;padding:22px 30px 10px}.vax-chart h2{font-size:22px}.vax-chart svg{height:145px}}
@media(max-width:800px){ #tab-files .action-buttons{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}#tab-files .btn-row{display:contents}#tab-files .btn-bar{padding:12px 8px;font-size:13px}.topbar{height:62px;padding:0 20px}.tabs{top:62px;left:0;right:0;bottom:auto;width:auto;height:54px;padding:0 8px;display:flex;flex-direction:row;gap:0;overflow-x:auto;overflow-y:hidden;background:#111015;border-bottom:1px solid #2a2730}.tab-item{width:auto;min-width:max-content;height:54px;min-height:54px;padding:0 19px;border-radius:0;font-size:14px;justify-content:center}.tab-item:before{display:none}.tab-item.active{background:transparent;border-bottom:2px solid var(--dravex-teal);box-shadow:none;color:#fff}.container{margin:0;padding:143px 18px 20px}.tab-content{max-width:none}#tab-console{display:none;grid-template-columns:1fr;gap:10px}#tab-console.active{display:grid}.server-header{grid-column:1;align-items:flex-end;margin:5px 0 2px}.server-title h1{font-size:22px}.server-title p{font-size:12px}.server-address-badge{font-size:10px;margin-top:8px}.power-row{gap:7px}.btn-power{min-width:84px;padding:10px 11px}.console-box{grid-column:1;grid-row:auto;height:520px}.cmd-input{grid-column:1;grid-row:auto}.mo-stats-header{grid-column:1;grid-row:auto;margin-top:5px}.mo-grid{grid-column:1;grid-row:auto;display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:0}.mo-net-row{grid-column:1;grid-row:auto;display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:0}.mo-card{min-height:82px}.mo-card-icon{display:block;font-size:20px;color:#ece8ee;margin-bottom:4px}.mo-card-value{font-size:14px}.service-links-card{grid-column:1}}
@media(max-width:520px){.topbar .brand{font-size:17px}.topbar{padding:0 14px}.topbar .icons{gap:17px}.container{padding-left:10px;padding-right:10px}.tab-item{padding:0 16px}.server-header{align-items:flex-start;flex-direction:column;gap:13px}.power-row{width:100%}.power-row .btn-power{flex:1}.console-box{height:520px}.mo-grid{grid-template-columns:1fr 1fr}.mo-net-row{grid-template-columns:1fr 1fr}.mo-net-item:last-child{grid-column:1 / -1}}
/* ============== PANELVEEX REFERENCE / NO SIDEBAR ============== */
/* The reference uses one compact horizontal navigation row; keep it on desktop and mobile. */
.tabs{
  position:fixed;top:62px;left:0;right:0;bottom:auto;width:auto;height:54px;
  padding:0 8px;display:flex;flex-direction:row;gap:0;overflow-x:auto;overflow-y:hidden;
  background:#111015;border-bottom:1px solid #2a2730;z-index:90;
}
.tab-item{
  width:auto;min-width:max-content;height:54px;min-height:54px;padding:0 19px;
  border-radius:0;font-size:14px;justify-content:center;display:flex;align-items:center;
}
.tab-item:before{display:none}
.tab-item.active{background:transparent;border-bottom:2px solid var(--dravex-teal);box-shadow:none;color:#fff}
.container{max-width:none;margin:0;padding:143px 25px 20px;min-height:100vh}
.tab-content{max-width:1090px;margin:0 auto}
.topbar .icons .ic[title="Menu"]{display:none}
.vax-sidebar,.vax-sidebar-backdrop{display:none!important}

/* File editing uses the exact console palette, monospace family and readable console scale. */
#edit-modal .modal-box{width:min(1100px,100%);max-height:94vh;background:#111015;border:1px solid #252a32;border-radius:3px}
#edit-modal .modal-head{background:#141316;border-bottom:1px solid #252a32;padding:13px 16px}
#edit-modal .modal-head h3{font-family:'Consolas','Monaco',monospace;font-size:12px;color:#c9c5cb;font-weight:400}
#edit-modal .modal-body{padding:0;background:#11151b}
#edit-modal .editor-textarea{
  display:block;width:100%;height:calc(94vh - 128px);min-height:520px;resize:none;
  margin:0;border:0;border-radius:0;background:#11151b;color:#c9c5cb;
  font-family:'Consolas','Monaco',monospace;font-size:12px;line-height:1.5;
  padding:14px;outline:none;white-space:pre;overflow:auto;tab-size:4;
}
#edit-modal .modal-foot{background:#141316;border-top:1px solid #252a32;padding:10px 14px}
#edit-modal .btn-action{font-family:'Consolas','Monaco',monospace;font-size:12px;border-radius:3px}
.fa-btns{opacity:1}
@media(max-width:800px){
  .container{padding:143px 18px 20px}
  #tab-console{grid-template-columns:1fr}
  #edit-modal{padding:6px}
  #edit-modal .modal-box{max-height:98vh}
  #edit-modal .editor-textarea{height:calc(98vh - 128px);min-height:420px;font-size:12px}
}
@media(max-width:520px){
  .topbar{padding:0 14px}
  .topbar .brand{font-size:17px}
  .tabs{padding:0 2px}
  .tab-item{padding:0 16px}
  .container{padding:143px 10px 20px}
}

#edit-modal{z-index:80;inset:116px 0 0;background:#141316;padding:0;align-items:stretch;justify-content:stretch}
#edit-modal .modal-box{width:100%;height:100%;max-height:none;background:#141316;border:0;border-radius:0;overflow:hidden}
#edit-modal .modal-head{display:none}
#edit-modal .modal-body{height:calc(100% - 92px);padding:0 30px;background:#141316}
#edit-modal .edit-breadcrumb{height:74px;padding:28px 0 10px;color:#eeeaf0;font-family:'Consolas','Monaco',monospace;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#edit-modal .editor-textarea{height:calc(100% - 74px);min-height:0;background:#222633;border:0;border-radius:5px;color:#e7e7e7;font-family:'Consolas','Monaco',monospace;font-size:16px;line-height:1.05;padding:14px 18px;white-space:pre;overflow:auto;tab-size:2}
#edit-modal .modal-foot.edit-actions{height:92px;background:#141316;border:0;padding:24px 30px;display:flex;justify-content:space-between;align-items:center;gap:30px}
#edit-modal #edit-language{height:58px;min-width:270px;background:#111015;border:1px solid #2b2a30;color:#f1edf2;padding:0 22px;font-family:Inter,'Segoe UI',sans-serif;font-size:18px}
#edit-modal .edit-save{height:58px;min-width:340px;border-radius:0;background:#527ab5;font-size:18px;font-weight:500;letter-spacing:.3px}
#edit-modal .edit-save:hover{background:#5d86c2}
@media(max-width:800px){
  .server-header{justify-content:flex-end}
  #edit-modal{inset:116px 0 0}
  #edit-modal .modal-body{height:calc(100% - 86px);padding:0 30px}
  #edit-modal .edit-breadcrumb{height:70px;padding-top:25px;font-size:15px}
  #edit-modal .editor-textarea{height:calc(100% - 70px);font-size:16px;line-height:1.05;padding:12px 14px}
  #edit-modal .modal-foot.edit-actions{height:86px;padding:14px 30px;gap:30px}
  #edit-modal #edit-language{height:58px;min-width:calc(50% - 15px);font-size:17px;padding:0 14px}
  #edit-modal .edit-save{height:58px;min-width:calc(50% - 15px);font-size:17px}
}
@media(max-width:520px){
  .server-header{margin-top:4px}
  #edit-modal .modal-body{padding:0 30px}
  #edit-modal .edit-breadcrumb{font-size:15px}
  #edit-modal .editor-textarea{font-size:15px;line-height:1.05}
  #edit-modal .modal-foot.edit-actions{padding:14px 30px;gap:30px}
  #edit-modal #edit-language,#edit-modal .edit-save{min-width:0;flex:1;font-size:15px}
}
</style>
</head>
<body>

<!-- ===== TOPBAR ===== -->
<div class="topbar">
  <div class="brand"><i>◁</i> <span class="lc">PANELVEEX</span> <i>▷</i></div>
  <div class="icons">
    <button class="ic" onclick="loadSearch()" title="Search"><i class="fas fa-search"></i></button>
    <button class="ic" onclick="location.href='/'" title="Servers"><i class="fas fa-layer-group"></i></button>
    <span class="avatar" title="''' + html.escape(MASTER_USERNAME) + r'''"><i class="fas fa-face-smile"></i></span>
    <button class="ic" onclick="location.href='/logout'" title="Logout"><i class="fas fa-right-from-bracket"></i></button>
  </div>
</div>
<!-- ===== TABS ===== -->
<div class="tabs" id="tabs">
  <div class="tab-item active" data-tab="console">Console</div>
  <div class="tab-item" data-tab="files">Files</div>
  <div class="tab-item" data-tab="databases">Databases</div>
  <div class="tab-item" data-tab="schedules">Schedules</div>
  ''' + master_tabs + r'''
</div>

<div class="container">

<!-- ===== CONSOLE TAB ===== -->
<div class="tab-content active" id="tab-console">
  <div class="server-header">
    <div class="server-title"><h1>''' + server_name + r'''</h1><p>''' + server_type + r'''</p></div>
    <div class="power-row">
      <button id="power-start" class="btn-power btn-start" onclick="powerAction('start')"><i class="fas fa-play"></i> Start</button>
      <button id="power-restart" class="btn-power btn-restart" onclick="powerAction('restart')" disabled><i class="fas fa-rotate"></i> Restart</button>
      <button id="power-stop" class="btn-power btn-stop" onclick="powerAction('stop')" disabled><i class="fas fa-stop"></i> Stop</button>
    </div>
  </div>

  <div class="console-box" id="console-output">container@pterodactyl~ Server marked as running...
</div>

  <div class="cmd-input">
    <span class="prompt">»</span>
    <input id="cmd-field" placeholder="Type a command..." onkeydown="if(event.key==='Enter') runCmd()">
  </div>

  <!-- ===== لوحة إحصائيات النظام — عربي RTL Dark Mode ===== -->
  <style>
    .mo-stats-header{display:none}
    .mo-stats-title{font-size:15px;font-weight:700;color:#c9d1d9;letter-spacing:.5px}
    .mo-stats-title span{color:#58a6ff}
    .mo-refresh-btn{background:#1f2937;border:1px solid #30363d;color:#8b949e;padding:5px 14px;border-radius:7px;font-size:12px;cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:6px}
    .mo-refresh-btn:hover{background:#58a6ff;color:#fff;border-color:#58a6ff}
    .mo-refresh-btn.spinning svg{animation:spin .7s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}
    .mo-grid{display:flex;flex-direction:column;gap:8px;direction:ltr}
    @media(max-width:700px){.mo-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mo-card{min-height:84px}}
    .mo-card{background:#211f27;border:1px solid #2a2730;border-radius:3px;padding:9px 10px;min-height:64px;display:grid;grid-template-columns:46px 1fr;grid-template-rows:auto auto;column-gap:11px;align-items:center;overflow:hidden}
    .mo-card:hover{border-color:#3a3640}
    .mo-card-icon{grid-row:1 / span 2;width:42px;height:42px;border-radius:3px;background:#111015;color:#f4f0f5;font-size:17px;display:flex;align-items:center;justify-content:center;margin:0}
    .mo-card-label{font-size:11px;color:#b2adb5;margin:0;font-weight:500}
    .mo-card-value{font-size:14px;font-weight:700;color:#f4f0f5;margin:2px 0 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .mo-card-value .unit{font-size:11px;color:#6e7681;font-weight:400}
    .mo-bar-bg{display:none}
    .mo-bar-fill{height:100%;border-radius:4px;transition:width .6s ease}
    .mo-bar-fill.green{background:linear-gradient(90deg,#238636,#3fb950)}
    .mo-bar-fill.yellow{background:linear-gradient(90deg,#9e6a03,#e3b341)}
    .mo-bar-fill.red{background:linear-gradient(90deg,#b91c1c,#f87171)}
    .mo-bar-fill.blue{background:linear-gradient(90deg,#1d4ed8,#60a5fa)}
    .mo-bar-fill.purple{background:linear-gradient(90deg,#7c3aed,#a78bfa)}
    .mo-card-sub{font-size:10px;color:#77727b;margin-top:2px;grid-column:2}
    .mo-card.wide{grid-column:span 2}
    .mo-net-row{display:none}
    .mo-net-item{flex:1;background:#0d1117;border-radius:7px;padding:8px 10px;border:1px solid #21262d}
    .mo-net-item .lbl{font-size:10px;color:#8b949e}
    .mo-net-item .val{font-size:13px;font-weight:700;color:#c9d1d9;margin-top:2px}
  </style>

  <div class="mo-stats-header">
    <div class="mo-stats-title"><i class="fas fa-chart-bar"></i> <span>إحصائيات النظام</span></div>
    <button class="mo-refresh-btn" id="mo-refresh-btn" onclick="moRefreshStats()">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
      تحديث
    </button>
  </div>

  <div class="mo-grid" id="mo-stats-grid">
    <div class="mo-card"><div class="mo-card-icon"><i class="fas fa-wifi"></i></div><div class="mo-card-label">Address</div><div class="mo-card-value" id="mo-ip-val">—</div><div class="mo-card-sub" id="mo-host-sub">—</div></div>
    <div class="mo-card"><div class="mo-card-icon"><i class="fas fa-clock"></i></div><div class="mo-card-label">Uptime</div><div class="mo-card-value" id="mo-uptime-val">—</div><div class="mo-card-sub">since server start</div></div>
    <div class="mo-card"><div class="mo-card-icon"><i class="fas fa-microchip"></i></div><div class="mo-card-label">CPU Load</div><div class="mo-card-value"><span id="mo-cpu-val">—</span> <span class="unit">%</span></div><div class="mo-card-sub" id="mo-cpu-sub">of 100%</div></div>
    <div class="mo-card"><div class="mo-card-icon"><i class="fas fa-memory"></i></div><div class="mo-card-label">Memory</div><div class="mo-card-value" id="mo-mem-val">—</div><div class="mo-card-sub" id="mo-mem-sub">of 1 GiB</div></div>
    <div class="mo-card"><div class="mo-card-icon"><i class="fas fa-hard-drive"></i></div><div class="mo-card-label">Disk</div><div class="mo-card-value" id="mo-disk-val">—</div><div class="mo-card-sub" id="mo-disk-sub">of 5 GiB</div></div>
    <div class="mo-card"><div class="mo-card-icon"><i class="fas fa-cloud-arrow-down"></i></div><div class="mo-card-label">Network (Inbound)</div><div class="mo-card-value" id="mo-netin-val">—</div></div>
    <div class="mo-card"><div class="mo-card-icon"><i class="fas fa-cloud-arrow-up"></i></div><div class="mo-card-label">Network (Outbound)</div><div class="mo-card-value" id="mo-netout-val">—</div></div>
  </div>
  <div class="vax-charts" id="vax-charts">
    <div class="vax-chart"><h2>CPU Load</h2><div class="chart-grid"><span>100.00%</span><span>50.00%</span><span>0.00%</span></div><svg viewBox="0 0 600 150" preserveAspectRatio="none"><path class="gridline" d="M0 18H600M0 75H600M0 145H600"/><polyline id="cpu-line" points="0,145 90,145 180,144 270,145 360,142 450,144 540,143 600,145"/></svg></div>
    <div class="vax-chart"><h2>Memory</h2><div class="chart-grid"><span>1200MiB</span><span>600MiB</span><span>0MiB</span></div><svg viewBox="0 0 600 150" preserveAspectRatio="none"><path class="gridline" d="M0 18H600M0 75H600M0 145H600"/><polyline id="mem-line" points="0,145 140,145 220,145 270,125 360,125 470,125 600,125"/></svg></div>
    <div class="vax-chart network-chart"><h2>Network <i class="fas fa-cloud-arrow-down down"></i><i class="fas fa-arrow-up up"></i></h2><div class="chart-grid"><span>700 Bytes</span><span>350 Bytes</span><span>0 Bytes</span></div><svg viewBox="0 0 600 150" preserveAspectRatio="none"><path class="gridline" d="M0 18H600M0 75H600M0 145H600"/><polyline id="net-in-line" class="cyan-line" points="0,145 160,145 250,140 330,115 450,120 540,115 570,35 600,120"/><polyline id="net-out-line" class="yellow-line" points="0,145 160,145 250,140 330,115 450,120 540,115 570,18 600,110"/></svg></div>
  </div>

  <!-- hidden legacy IDs for backward compat -->
  <div style="display:none">
    <span id="s-ip"></span><span id="s-addr"></span><span id="s-uptime"></span>
    <span id="s-cpu"></span><span id="s-mem"></span><span id="s-disk"></span>
    <span id="s-in"></span><span id="s-out"></span><span id="s-host"></span>
    <span id="port-display"></span>
  </div>

  <div class="stats-grid" id="stats-grid" style="display:none"></div>

</div>

<!-- ===== FILES TAB ===== -->
<div class="tab-content" id="tab-files">
  <div class="action-buttons">
    <button class="btn-bar btn-create-dir" onclick="createDir()">Create Directory</button>
    <div class="btn-row">
      <button class="btn-bar btn-upload" onclick="document.getElementById('file-up').click()">Upload</button>
      <button class="btn-bar btn-newfile" onclick="newFile()">New File</button>
    </div>
    <div class="btn-row file-tools-row">
      <button class="btn-bar btn-select" onclick="selectAllFiles()"><i class="fas fa-check-double"></i> Select All</button>
      <button class="btn-bar btn-clear-selection" onclick="clearFileSelection()"><i class="fas fa-xmark"></i> Clear Selection</button>
      <button class="btn-bar btn-archive" onclick="archiveSelected()"><i class="fas fa-file-zipper"></i> Archive</button>
      <button class="btn-bar btn-delete-selected" onclick="deleteSelectedFiles()"><i class="fas fa-trash-can"></i> Delete Selected</button>
    </div>
    <input type="file" id="file-up" style="display:none" onchange="uploadFile(this)">
  </div>

  <div class="breadcrumb" id="breadcrumb">/ home / container /</div>

  <div class="file-list" id="file-list"></div>
</div>

<!-- ===== DATABASES TAB ===== -->
<div class="tab-content" id="tab-databases">
  <div class="section-card">
    <div class="section-head">DATABASES</div>
    <div class="section-body">
      <p style="color:#9aa9b3;font-size:13px;margin-bottom:12px">Manage SQLite / JSON databases stored in your panel folder.</p>
      <div class="field-block">
        <label>Database Name</label>
        <input id="db-name" placeholder="my_database">
      </div>
      <div class="row-end"><button class="btn-action" onclick="createDB()">Create Database</button></div>
    </div>
  </div>
  <div id="db-list"></div>
</div>

<!-- ===== SCHEDULES TAB ===== -->
<div class="tab-content" id="tab-schedules">
  <div class="section-card">
    <div class="section-head">CREATE SCHEDULE</div>
    <div class="section-body">
      <div class="field-block"><label>Name</label><input id="sch-name" placeholder="Daily backup"></div>
      <div class="field-block"><label>Command</label><input id="sch-cmd" placeholder="echo hello"></div>
      <div class="field-block"><label>Cron</label><input id="sch-cron" placeholder="* * * * *" value="* * * * *"></div>
      <div class="row-end"><button class="btn-action" onclick="addSchedule()">Add Schedule</button></div>
    </div>
  </div>
  <div id="sch-list"></div>
</div>

''' + (r'''
<!-- ===== USERS TAB (master only) ===== -->
<div class="tab-content" id="tab-users">
  <div class="section-card">
    <div class="section-head">ADD USER</div>
    <div class="section-body">
      <div class="field-block"><label>Username</label><input id="u-name" placeholder="username"></div>
      <div class="field-block"><label>Password</label><input id="u-pass" type="password" placeholder="password"></div>
      <div class="field-block"><label>Max Sessions</label><input id="u-max" type="number" value="1"></div>
      <div class="field-block"><label>Max Servers (عدد السيرفرات)</label>
        <select id="u-maxsrv" style="width:100%;padding:10px 12px;background:#1f2933;border:1px solid #3a4a55;border-radius:4px;color:#fff;font-size:13px;outline:none">
          <option value="1">1 Server</option>
          <option value="2">2 Servers</option>
          <option value="3">3 Servers</option>
          <option value="5">5 Servers</option>
          <option value="10">10 Servers</option>
          <option value="999">Unlimited</option>
        </select>
      </div>
      <div class="field-block"><label>Server Name</label><input id="u-server-name" placeholder="Leave blank = no server" value=""></div>
      <div class="field-block"><label>Main File (ملف التشغيل الأساسي)</label><input id="u-main" placeholder="main.py" value="main.py"></div>
      <div class="row-end"><button class="btn-action" onclick="addUser()">Add User</button></div>
    </div>
  </div>
  <!-- Edit User Modal -->
  <div class="modal" id="edit-user-modal">
    <div class="modal-box">
      <div class="modal-head">
        <h3>Edit User</h3>
        <button class="close" onclick="closeModal('edit-user-modal')">×</button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="eu-name">
        <div class="field-block"><label>New Password (leave blank to keep)</label><input id="eu-pass" type="password" placeholder="new password"></div>
        <div class="field-block"><label>Max Sessions</label><input id="eu-max" type="number"></div>
        <div class="field-block"><label>Max Servers</label>
          <select id="eu-maxsrv" style="width:100%;padding:10px 12px;background:#1f2933;border:1px solid #3a4a55;border-radius:4px;color:#fff;font-size:13px;outline:none">
            <option value="1">1 Server</option>
            <option value="2">2 Servers</option>
            <option value="3">3 Servers</option>
            <option value="5">5 Servers</option>
            <option value="10">10 Servers</option>
            <option value="999">Unlimited</option>
          </select>
        </div>
        <div class="field-block"><label>Server Name</label><input id="eu-server-name" placeholder="Leave blank = no server"></div>
        <div class="field-block"><label>Main File</label><input id="eu-main" placeholder="main.py"></div>
      </div>
      <div class="modal-foot">
        <button class="btn-action gray" onclick="closeModal('edit-user-modal')">Cancel</button>
        <button class="btn-action" onclick="saveEditUser()">Save Changes</button>
      </div>
    </div>
  </div>
  <div id="user-list"></div>
</div>

<!-- ===== BACKUPS TAB ===== -->
<div class="tab-content" id="tab-backups">
  <div class="section-card">
    <div class="section-head">BACKUPS</div>
    <div class="section-body">
      <p style="color:#9aa9b3;font-size:13px;margin-bottom:12px">Create compressed snapshots (.tar.gz) of your panel data.</p>
      <div class="row-end"><button class="btn-action" onclick="createBackup()">Create Backup</button></div>
    </div>
  </div>
  <div id="backup-list"></div>
</div>

<!-- ===== NETWORK TAB ===== -->
<div class="tab-content" id="tab-network">
  <div class="section-card">
    <div class="section-head">PRIMARY ALLOCATION</div>
    <div class="section-body">
      <div class="port-card">
        <div class="port-head">
          <div class="port-host" id="primary-host">node70.lunes.ho...</div>
          <div class="port-badge" id="primary-port">3177</div>
        </div>
        <div class="field-block">
          <label>Notes</label>
          <textarea placeholder="Notes"></textarea>
        </div>
        <div class="row-end"><button class="btn-action">Primary</button></div>
      </div>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">ADDITIONAL PORTS (Multi-port for Flask apps)</div>
    <div class="section-body">
      <div class="field-block"><label>Port Number</label><input id="new-port" type="number" placeholder="5000"></div>
      <div class="field-block"><label>Description</label><input id="new-port-note" placeholder="My Flask App"></div>
      <div class="row-end"><button class="btn-action" onclick="addPort()">Add Port</button></div>
    </div>
  </div>
  <div id="port-list"></div>

  <div class="section-card">
    <div class="section-head">PORT SCANNER</div>
    <div class="section-body">
      <div class="field-block"><label>Host</label><input id="scan-host" value="127.0.0.1"></div>
      <div class="field-block"><label>Ports (comma separated)</label><input id="scan-ports" value="22,80,443,3177,5000,8080"></div>
      <div class="row-end"><button class="btn-action" onclick="scanPorts()">Scan</button></div>
      <div id="scan-out" style="margin-top:10px;font-family:monospace;font-size:12px;color:#9aa9b3"></div>
    </div>
  </div>
</div>

<!-- ===== STARTUP TAB ===== -->
<div class="tab-content" id="tab-startup">
  <div class="section-card">
    <div class="section-head">STARTUP COMMAND</div>
    <div class="section-body">
      <div class="field-block">
        <label>Main File (ملف التشغيل الأساسي)</label>
        <div style="display:flex;gap:8px;align-items:center">
          <input id="startup-cmd" value="main.py" style="flex:1">
          <button class="btn-action" style="flex-shrink:0" onclick="runMainFile()">&#9654; Run Main</button>
          <button class="btn-action gray" style="flex-shrink:0" onclick="loadMainFile()">Refresh</button>
        </div>
        <p style="color:#7a8c98;font-size:11px;margin-top:6px">This is the main startup file. Click 'Main' button on any file in Files tab to change it.</p>
      </div>
    </div>
  </div>
  <div class="section-card">
    <div class="section-head">DOCKER IMAGE</div>
    <div class="section-body">
      <div class="field-block">
        <select id="docker-img">
          <option>ghcr.io/parkervcp/yolks:python_3.13</option>
          <option>ghcr.io/parkervcp/yolks:python_3.11</option>
          <option>ghcr.io/parkervcp/yolks:nodejs_20</option>
        </select>
        <p style="color:#7a8c98;font-size:11px;margin-top:6px">Advanced feature — choose a Docker image (cosmetic on Replit).</p>
      </div>
    </div>
  </div>
  <div class="section-card">
    <div class="section-head">VARIABLES</div>
    <div class="section-body">
      <div class="field-block">
        <label>STARTUP COMMAND</label>
        <input value="python3 vps_panel.py" readonly>
        <p style="color:#7a8c98;font-size:11px;margin-top:6px">the command to run to start it up</p>
      </div>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">PIP PACKAGE INSTALLER</div>
    <div class="section-body">
      <div class="field-block"><label>Package</label><input id="pip-pkg" placeholder="flask"></div>
      <div class="row-end"><button class="btn-action" onclick="installPip()">Install</button></div>
    </div>
  </div>
</div>
''' if is_master else r'''
''') + r'''

<!-- ===== SETTINGS TAB ===== -->
<div class="tab-content" id="tab-settings">
  <div class="section-card">
    <div class="section-head">SFTP DETAILS</div>
    <div class="section-body">
      <div class="field-block">
        <label>Server Address</label>
        <input id="sftp-addr" readonly>
      </div>
      <div class="field-block">
        <label>Username</label>
        <input id="sftp-user" readonly>
      </div>
      <p style="color:#7a8c98;font-size:12px">Your SFTP password is the same as the password you use to access the panel.</p>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">DEBUG INFORMATION</div>
    <div class="section-body">
      <div class="field-block"><label>Node</label><input id="dbg-node" readonly></div>
      <div class="field-block"><label>Server ID</label><input id="dbg-id" readonly></div>
      <div class="field-block"><label>Platform</label><input id="dbg-plat" readonly></div>
    </div>
  </div>

  ''' + (r'''
  <div class="section-card">
    <div class="section-head">CHANGE MASTER CREDENTIALS</div>
    <div class="section-body">
      <div class="field-block"><label>New Username</label><input id="m-newuser" placeholder="new username"></div>
      <div class="row-end"><button class="btn-action" onclick="changeUser()">Save Username</button></div>
      <hr style="margin:14px 0;border:0;border-top:1px solid #3a4a55">
      <div class="field-block"><label>Current Password</label><input id="m-curpass" type="password"></div>
      <div class="field-block"><label>New Password</label><input id="m-newpass" type="password"></div>
      <div class="row-end"><button class="btn-action" onclick="changePass()">Save Password</button></div>
      <hr style="margin:14px 0;border:0;border-top:1px solid #3a4a55">
      <div class="field-block"><label>Server Port</label><input id="m-port" type="number"></div>
      <div class="row-end"><button class="btn-action" onclick="changePort()">Save Port (restarts panel)</button></div>
      <hr style="margin:14px 0;border:0;border-top:1px solid #3a4a55">
      <div class="row-end"><button class="btn-action danger" onclick="restartPanel()">Restart Panel</button></div>
    </div>
  </div>

  <div class="section-card">
    <div class="section-head">SYSTEM ACTIONS</div>
    <div class="section-body">
      <div class="row-end" style="gap:8px">
        <button class="btn-action gray" onclick="sysAction('clean')">Clean Memory</button>
        <button class="btn-action gray" onclick="sysAction('update')">apt update</button>
        <button class="btn-action gray" onclick="clearLogs()">Clear Logs</button>
      </div>
    </div>
  </div>
  ''' if is_master else r'''

  <!-- ===== USER SERVER SETTINGS ===== -->
  <div class="section-card">
    <div class="section-head">SERVER SETTINGS</div>
    <div class="section-body">
      <div class="field-block">
        <label>Runtime Type</label>
        <select id="u-runtime" onchange="updateRuntimeVersions()" style="width:100%;background:#1a2530;color:#d0dde5;border:1px solid #3a4a55;border-radius:6px;padding:8px 10px;font-size:13px">
          <option value="python">🐍 Python</option>
          <option value="nodejs">🟨 JavaScript (Node.js)</option>
        </select>
      </div>
      <div class="field-block">
        <label>Version</label>
        <select id="u-runtime-ver" style="width:100%;background:#1a2530;color:#d0dde5;border:1px solid #3a4a55;border-radius:6px;padding:8px 10px;font-size:13px">
          <option value="3.11">3.11 (default)</option>
          <option value="3.12">3.12</option>
          <option value="3.10">3.10</option>
          <option value="3.9">3.9</option>
        </select>
      </div>
      <div class="field-block">
        <label>Main Startup File</label>
        <input id="u-main-file" placeholder="main.py" style="width:100%">
      </div>
      <div class="row-end">
        <button class="btn-action" onclick="saveUserSettings()"><i class="fas fa-save"></i> Save Settings</button>
      </div>
    </div>
  </div>

  <!-- ===== CHANGE PASSWORD ===== -->
  <div class="section-card">
    <div class="section-head">CHANGE PASSWORD</div>
    <div class="section-body">
      <div class="field-block"><label>Current Password</label><input id="u-curpass" type="password" placeholder="Current password"></div>
      <div class="field-block"><label>New Password</label><input id="u-newpass" type="password" placeholder="New password (min 6 chars)"></div>
      <div class="field-block"><label>Confirm New Password</label><input id="u-conpass" type="password" placeholder="Repeat new password"></div>
      <div class="row-end"><button class="btn-action" onclick="changeUserPass()"><i class="fas fa-key"></i> Change Password</button></div>
    </div>
  </div>

  <!-- ===== DANGER ZONE ===== -->
  <div class="section-card" style="border-color:#e5393566">
    <div class="section-head" style="color:#e53935">⚠️ DANGER ZONE</div>
    <div class="section-body">
      <p style="color:#9aa9b3;font-size:12px;margin-bottom:14px">Deleting your server will permanently remove all your files, databases, and data. <strong style="color:#e53935">This cannot be undone.</strong></p>
      <div class="field-block"><label>Enter Your Password to Confirm</label><input id="u-del-pass" type="password" placeholder="Your password"></div>
      <div class="row-end"><button class="btn-action danger" onclick="deleteMyServer()"><i class="fas fa-trash-alt"></i> Delete My Server</button></div>
    </div>
  </div>

  ''') + r'''
</div>

<!-- ===== ACTIVITY TAB (NEW - shows logins/logouts/operations) ===== -->
<div class="tab-content" id="tab-activity">
  <div class="section-card">
    <div class="section-head">ACTIVITY FEED</div>
    <div class="section-body" style="padding:8px">
      <p style="color:#9aa9b3;font-size:12px;padding:6px 10px">Latest logins, logouts and operations performed by users.</p>
      <div class="row-end" style="padding:0 10px 10px"><button class="btn-action gray" onclick="loadActivity()">Refresh</button></div>
    </div>
  </div>
  <div id="activity-list"></div>
</div>

<!-- ===== OWNER TAB (Master Only) ===== -->
''' + (r'''
<div class="tab-content" id="tab-owner">

  <!-- Hero -->
  <div class="owner-hero">
    <h2><i class="fas fa-crown"></i> Owner Control Panel</h2>
    <p>Full control over the panel, users, bot, and system settings</p>
    <div style="margin-top:10px;display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap">
      <div id="bot-status-badge"><span class="bot-unlinked-badge"><i class="fas fa-exclamation-triangle" style="color:#f39c12"></i> Bot Not Linked</span></div>
      <span id="maint-status-badge" style="display:none" class="bot-unlinked-badge"><i class="fas fa-wrench"></i> Maintenance ON</span>
    </div>
  </div>

  <!-- Stats (6 cards) -->
  <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:14px" id="ow-stats-grid">
    <div class="owner-stat"><div class="o-num" id="ow-users">0</div><div class="o-lbl"><i class="fas fa-users"></i> Users</div></div>
    <div class="owner-stat"><div class="o-num" id="ow-sessions">0</div><div class="o-lbl"><i class="fas fa-circle" style="color:#2ecc71"></i> Online</div></div>
    <div class="owner-stat"><div class="o-num" id="ow-banned">0</div><div class="o-lbl"><i class="fas fa-ban" style="color:#e53935"></i> Banned</div></div>
    <div class="owner-stat"><div class="o-num" id="ow-bots">0</div><div class="o-lbl"><i class="fas fa-robot"></i> Processes</div></div>
    <div class="owner-stat"><div class="o-num" id="ow-zips">0</div><div class="o-lbl"><i class="fas fa-box-open"></i> ZIPs</div></div>
    <div class="owner-stat"><div class="o-num" id="ow-servers">0</div><div class="o-lbl"><i class="fas fa-desktop"></i> Servers</div></div>
  </div>
  <style>
    @media(max-width:700px){ #ow-stats-grid{grid-template-columns:repeat(3,1fr)!important}}
    @media(max-width:430px){ #ow-stats-grid{grid-template-columns:repeat(2,1fr)!important}}
  </style>

  <!-- Online Users -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-circle" style="color:#2ecc71;font-size:10px"></i> ONLINE USERS
      <button class="btn-action gray" style="padding:4px 10px;font-size:11px;margin-left:auto" onclick="loadOwnerPanel()"><i class="fas fa-sync-alt"></i> Refresh</button>
    </div>
    <div class="section-body">
      <div id="ow-sessions-list"><div style="color:#9aa9b3;font-size:13px">Loading...</div></div>
    </div>
  </div>

  <!-- User Management -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-users-cog"></i> USER MANAGEMENT</div>
    <div class="section-body">
      <!-- Add User row -->
      <div style="background:#1a242c;border:1px solid #2a3640;border-radius:6px;padding:12px;margin-bottom:12px">
        <div class="owner-section-title" style="margin-bottom:10px"><i class="fas fa-user-plus"></i> Add New User</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">
          <div class="field-block" style="margin:0"><label>Username</label><input id="ow-new-uname" placeholder="username"></div>
          <div class="field-block" style="margin:0"><label>Password</label><input id="ow-new-pass" type="password" placeholder="password"></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px">
          <div class="field-block" style="margin:0"><label>Max Sessions</label><input id="ow-new-msess" type="number" value="999" min="1"></div>
          <div class="field-block" style="margin:0"><label>Max Servers</label><input id="ow-new-msrv" type="number" value="1" min="1"></div>
          <div class="field-block" style="margin:0"><label>Main File</label><input id="ow-new-mfile" value="main.py"></div>
        </div>
        <div class="row-end"><button class="btn-action" onclick="ownerAddUser()"><i class="fas fa-user-plus"></i> Add User</button></div>
      </div>
      <!-- User table -->
      <div style="overflow-x:auto">
        <table class="owner-user-table">
          <thead><tr>
            <th>Username</th><th>Status</th><th>Sessions</th><th>Servers</th><th>Main File</th><th>Actions</th>
          </tr></thead>
          <tbody id="ow-user-tbody"><tr><td colspan="6" style="color:#9aa9b3;padding:14px">Loading users...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Maintenance Mode -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-wrench"></i> MAINTENANCE MODE</div>
    <div class="section-body">
      <div class="maint-toggle">
        <div>
          <div class="mt-label">Maintenance Mode</div>
          <div class="mt-sub">When enabled, users see a maintenance page instead of the panel</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" id="maint-toggle-chk" onchange="toggleMaintenance()">
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="field-block" style="margin-top:10px">
        <label>Maintenance Message (shown to users)</label>
        <textarea id="maint-msg" rows="3" placeholder="نحن نعمل على تحديث النظام، يرجى العودة لاحقاً"></textarea>
      </div>
      <div class="row-end">
        <button class="btn-action" onclick="saveMaintMsg()">Save Message</button>
      </div>
    </div>
  </div>

  <!-- Telegram Bot Link -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-robot"></i> TELEGRAM BOT LINK</div>
    <div class="section-body">
      <p style="color:#9aa9b3;font-size:13px;margin-bottom:14px">Link your Telegram bot to enable remote control via Telegram.</p>
      <div class="field-block">
        <label>Bot Token</label>
        <input id="tg-token" type="password" placeholder="123456:ABC-DEF..." autocomplete="off">
      </div>
      <div class="field-block">
        <label>Your Telegram ID (Owner ID)</label>
        <input id="tg-ownerid" placeholder="123456789">
      </div>
      <div class="row-end" style="gap:8px">
        <button class="btn-action gray" onclick="unlinkBot()">Unlink Bot</button>
        <button class="btn-action" onclick="linkBot()">Link &amp; Activate</button>
      </div>
      <div id="bot-link-status" style="margin-top:10px;font-size:13px;color:#9aa9b3"></div>
    </div>
  </div>

  <!-- Bot Control Panel (shown only when linked) -->
  <div class="section-card" id="bot-control-panel" style="display:none">
    <div class="section-head"><i class="fas fa-gamepad"></i> BOT CONTROL PANEL
      <span id="bot-username-badge" style="margin-left:8px;font-size:11px;color:#29c7d3;font-weight:400"></span>
    </div>
    <div class="section-body">
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px">
        <button class="btn-action" style="background:#65c466" onclick="botAction(&#39;start&#39;)"><i class="fas fa-play"></i> Start Bot</button>
        <button class="btn-action gray" onclick="botAction(&#39;restart&#39;)"><i class="fas fa-sync-alt"></i> Restart Bot</button>
        <button class="btn-action danger" onclick="botAction(&#39;stop&#39;)"><i class="fas fa-stop"></i> Stop Bot</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px">
        <button class="btn-action gray" onclick="downloadAllZips()"><i class="fas fa-download"></i> Download All ZIPs</button>
        <button class="btn-action gray" onclick="refreshBotStats()"><i class="fas fa-sync-alt"></i> Refresh Stats</button>
      </div>
      <div id="bot-console" style="background:#0d1419;border:1px solid #2a3640;border-radius:4px;padding:12px;font-family:monospace;font-size:12px;color:#c8d4dc;height:160px;overflow-y:auto;white-space:pre-wrap;margin-bottom:10px">Bot console ready...
</div>
      <div style="display:flex;gap:8px">
        <input id="bot-cmd-input" placeholder="Send command to bot..." style="flex:1;padding:10px;background:#1a242c;border:1px solid #2a3640;border-radius:4px;color:#fff;outline:none;font-size:13px" onkeydown="if(event.key===&#39;Enter&#39;)sendBotCmd()">
        <button class="btn-action" onclick="sendBotCmd()"><i class="fas fa-chevron-right"></i> Send</button>
      </div>
    </div>
  </div>

  <!-- ZIP Files Manager -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-box-open"></i> ZIP FILES MANAGER</div>
    <div class="section-body">
      <p style="color:#9aa9b3;font-size:13px;margin-bottom:10px">All ZIP files uploaded by users across the panel.</p>
      <div class="row-end" style="margin-bottom:10px">
        <button class="btn-action gray" onclick="loadOwnerZips()"><i class="fas fa-sync-alt"></i> Refresh</button>
        <button class="btn-action" onclick="downloadAllZips()" style="margin-left:8px"><i class="fas fa-download"></i> Download All</button>
      </div>
      <div id="owner-zip-list"></div>
    </div>
  </div>

  <!-- Announcements -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-bullhorn"></i> ANNOUNCEMENTS</div>
    <div class="section-body">
      <div class="field-block">
        <label>New Announcement</label>
        <textarea id="announce-text" rows="2" placeholder="Write your announcement here..."></textarea>
      </div>
      <div class="row-end"><button class="btn-action" onclick="addAnnouncement()"><i class="fas fa-paper-plane"></i> Send Announcement</button></div>
      <div id="announce-list" style="margin-top:14px"></div>
    </div>
  </div>

  <!-- Panel Settings -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-cog"></i> PANEL SETTINGS</div>
    <div class="section-body">
      <div class="creds-grid">
        <div class="field-block" style="margin:0 0 10px"><label>Panel Name</label><input id="panel-name-inp" placeholder="PANELVEEX"></div>
        <div class="field-block" style="margin:0 0 10px"><label>Welcome Message</label><input id="panel-welcome-inp" placeholder="Welcome to the panel"></div>
      </div>
      <div class="row-end"><button class="btn-action" onclick="savePanelSettings()"><i class="fas fa-save"></i> Save Settings</button></div>
    </div>
  </div>

  <!-- Master Credentials -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-key"></i> MASTER CREDENTIALS</div>
    <div class="section-body">
      <div style="background:#1a242c;border:1px solid #2a3640;border-radius:6px;padding:12px;margin-bottom:10px">
        <div class="owner-section-title"><i class="fas fa-user-shield"></i> Change Username</div>
        <div class="field-block"><label>New Username</label><input id="mc-new-uname" placeholder="new username"></div>
        <div class="row-end"><button class="btn-action" onclick="ownerChangeUsername()"><i class="fas fa-check"></i> Update</button></div>
      </div>
      <div style="background:#1a242c;border:1px solid #2a3640;border-radius:6px;padding:12px;margin-bottom:10px">
        <div class="owner-section-title"><i class="fas fa-lock"></i> Change Password</div>
        <div class="creds-grid">
          <div class="field-block" style="margin:0 0 8px"><label>Current Password</label><input id="mc-cur-pass" type="password" placeholder="current password"></div>
          <div class="field-block" style="margin:0 0 8px"><label>New Password</label><input id="mc-new-pass" type="password" placeholder="new password"></div>
        </div>
        <div class="row-end"><button class="btn-action" onclick="ownerChangePassword()"><i class="fas fa-lock"></i> Change Password</button></div>
      </div>
      <div style="background:#1a242c;border:1px solid #2a3640;border-radius:6px;padding:12px">
        <div class="owner-section-title"><i class="fas fa-network-wired"></i> Change Panel Port</div>
        <div class="field-block"><label>Port Number</label><input id="mc-port" type="number" placeholder="3178" min="1024" max="65535"></div>
        <div class="row-end"><button class="btn-action" onclick="ownerChangePort()"><i class="fas fa-bolt"></i> Apply &amp; Restart</button></div>
      </div>
    </div>
  </div>

  <!-- Broadcast Message -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-satellite-dish"></i> BROADCAST TO ALL USERS</div>
    <div class="section-body">
      <div class="field-block">
        <label>Message</label>
        <textarea id="broadcast-msg" rows="3" placeholder="Message to broadcast to all users via Telegram..."></textarea>
      </div>
      <div class="row-end"><button class="btn-action" onclick="broadcastMsg()"><i class="fas fa-satellite-dish"></i> Broadcast</button></div>
    </div>
  </div>

  <!-- BOT LOCK -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-lock"></i> BOT LOCK (MAINTENANCE)</div>
    <div class="section-body">
      <div class="maint-toggle">
        <div>
          <div class="mt-label">Lock Bot (Maintenance Mode)</div>
          <div class="mt-sub">When enabled, regular users see maintenance message and cannot use the bot</div>
        </div>
        <label class="toggle-switch">
          <input type="checkbox" id="bot-lock-chk" onchange="toggleBotLock()">
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="field-block" style="margin-top:10px">
        <label>Maintenance Message (shown to users in bot)</label>
        <input id="bot-lock-msg" placeholder="البوت في وضع الصيانة مؤقتاً 🔧">
      </div>
      <div class="row-end">
        <button class="btn-action" onclick="saveBotLockMsg()"><i class="fas fa-save"></i> Save Message</button>
      </div>
    </div>
  </div>

  <!-- STAR PAYMENT -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-star"></i> TELEGRAM STARS PAYMENT</div>
    <div class="section-body">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div class="field-block">
          <label>Stars Amount</label>
          <input id="star-price" type="number" min="1" placeholder="1">
        </div>
        <div class="field-block">
          <label>Payment Label</label>
          <input id="star-label" placeholder="دعم بنجمة">
        </div>
      </div>
      <div class="row-end">
        <button class="btn-action" onclick="saveStarPayment()"><i class="fas fa-save"></i> Save Settings</button>
      </div>
    </div>
  </div>

  <!-- PROOF CHANNEL -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-broadcast-tower"></i> PROOF CHANNEL (قناة الإثبات)</div>
    <div class="section-body">
      <p style="color:#9aa9b3;font-size:12px;margin-bottom:10px">When a user creates a server, a notification is sent to this channel automatically. Make sure the bot is an admin in the channel.</p>
      <div class="field-block">
        <label>Channel ID or Username</label>
        <input id="proof-channel" placeholder="@my_channel or -1001234567890">
      </div>
      <div class="row-end" style="gap:8px">
        <button class="btn-action gray" onclick="document.getElementById('proof-channel').value=''; saveProofChannel()"><i class="fas fa-times"></i> Remove</button>
        <button class="btn-action" onclick="saveProofChannel()"><i class="fas fa-save"></i> Save Channel</button>
      </div>
    </div>
  </div>

  <!-- SUPPORT TICKETS -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-headset"></i> SUPPORT TICKETS
      <button class="btn-action gray" style="padding:4px 10px;font-size:11px;margin-left:auto" onclick="loadSupportTickets()"><i class="fas fa-sync-alt"></i> Refresh</button>
    </div>
    <div class="section-body">
      <div id="support-tickets-list"><div style="color:#9aa9b3;font-size:13px">Loading...</div></div>
    </div>
  </div>

  <!-- Recent Activity Feed -->
  <div class="section-card">
    <div class="section-head"><i class="fas fa-stream"></i> RECENT ACTIVITY
      <button class="btn-action gray" style="padding:4px 10px;font-size:11px;margin-left:auto" onclick="loadOwnerActivityFeed()"><i class="fas fa-sync-alt"></i> Refresh</button>
    </div>
    <div class="section-body">
      <div id="ow-activity-feed"><div style="color:#9aa9b3;font-size:13px">Loading...</div></div>
    </div>
  </div>

  <!-- Danger Zone -->
  <div class="section-card" style="border-color:#e5393544">
    <div class="section-head" style="color:#e53935">&#9888; DANGER ZONE</div>
    <div class="section-body">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <button class="btn-action danger" onclick="ownerAction(&#39;clear_all_logs&#39;)"><i class="fas fa-trash-alt"></i> Clear All Logs</button>
        <button class="btn-action danger" onclick="ownerAction(&#39;kick_all_users&#39;)"><i class="fas fa-ban"></i> Kick All Users</button>
        <button class="btn-action danger" onclick="ownerAction(&#39;reset_stats&#39;)"><i class="fas fa-sync-alt"></i> Reset Stats</button>
        <button class="btn-action danger" onclick="ownerAction(&#39;restart_panel&#39;)"><i class="fas fa-bolt"></i> Restart Panel</button>
        <button class="btn-action gray" onclick="createBackup()" style="grid-column:span 2"><i class="fas fa-archive"></i> Create Backup Now</button>
      </div>
    </div>
  </div>

</div>
''' if is_master else '') + r'''

<div class="foot-pterod"><a href="https://t.me/V2X_2" target="_blank" style="color:#29c7d3;text-decoration:none">♘ king panelveex</a></div>
</div>

<!-- ===== FILE EDIT MODAL ===== -->
<div class="modal" id="edit-modal">
  <div class="modal-box">
    <div class="modal-head">
      <h3 id="edit-title">Edit File</h3>
      <button class="close" onclick="closeModal('edit-modal')">×</button>
    </div>
    <div class="modal-body">
      <div class="edit-breadcrumb" id="edit-breadcrumb"></div>
      <textarea class="editor-textarea" id="edit-content" spellcheck="false"></textarea>
    </div>
    <div class="modal-foot edit-actions">
      <select id="edit-language" aria-label="Language">
        <option>JavaScript</option><option>JSON</option><option>Lua</option><option>Markdown</option><option>Python</option><option>Plain Text</option>
      </select>
      <button class="btn-action edit-save" onclick="saveEdit()">SAVE CONTENT</button>
    </div>
  </div>
</div>

<!-- ===== RUN OUTPUT MODAL ===== -->
<div class="modal" id="run-modal">
  <div class="modal-box">
    <div class="modal-head">
      <h3>Process Output</h3>
      <button class="close" onclick="closeRun()">×</button>
    </div>
    <div class="modal-body">
      <div class="console-box" id="run-output" style="height:300px"></div>
      <div class="cmd-input">
        <span class="prompt">»</span>
        <input id="run-input" placeholder="Send input..." onkeydown="if(event.key==='Enter') sendRunInput()">
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn-action danger" onclick="stopRun()">Stop</button>
      <button class="btn-action gray" onclick="closeRun()">Close</button>
    </div>
  </div>
</div>

<script>
const IS_MASTER = ''' + ('true' if is_master else 'false') + r''';
const USER_PATH = ''' + json.dumps(get_user_path(MASTER_USERNAME if is_master else (username or 'user'))) + r''';
let currentPath = USER_PATH;
let currentEditPath = null;
let currentRunPid = null;
let runPoll = null;

/* =========== TABS =========== */
function toggleVaxSidebar(){document.getElementById('vax-sidebar')?.classList.toggle('open');document.getElementById('vax-sidebar-backdrop')?.classList.toggle('open')}
function vaxUpdateCharts(){const jitter=()=>Math.round(136+Math.random()*10);const cpu=document.getElementById('cpu-line'),mem=document.getElementById('mem-line');if(cpu)cpu.setAttribute('points',`0,145 90,${jitter()} 180,${jitter()} 270,${jitter()} 360,${jitter()} 450,${jitter()} 540,${jitter()} 600,${jitter()}`);if(mem)mem.setAttribute('points',`0,145 140,145 220,145 270,${120+Math.random()*15} 360,${120+Math.random()*15} 470,${120+Math.random()*15} 600,${120+Math.random()*15}`)}
setInterval(vaxUpdateCharts,4500);
document.querySelectorAll('.tab-item').forEach(t=>{
  t.addEventListener('click',()=>{
    document.querySelectorAll('.tab-item').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    const tn = t.dataset.tab;
    const el = document.getElementById('tab-'+tn);
    if(el) el.classList.add('active');
    onTabChange(tn);
  });
});
function onTabChange(t){
  if(t==='files') loadFiles();
  if(t==='activity') loadActivity();
  if(t==='users' && IS_MASTER) loadUsers();
  if(t==='backups' && IS_MASTER) loadBackups();
  if(t==='schedules') loadSchedules();
  if(t==='network' && IS_MASTER) loadPorts();
  if(t==='settings'){ loadSettings(); if(!IS_MASTER) loadUserSettings(); }
  if(t==='startup') loadMainFile();
  if(t==='owner' && IS_MASTER) loadOwnerPanel();
}

/* =========== TOAST =========== */
function toast(msg, err){
  const d=document.createElement('div');
  d.className='toast'+(err?' error':'');
  d.textContent=msg;
  document.body.appendChild(d);
  setTimeout(()=>d.remove(),3000);
}

/* =========== CONSOLE / STATS =========== */
function moBarColor(pct){
  if(pct < 60) return 'green';
  if(pct < 85) return 'yellow';
  return 'red';
}
function moFmtUptime(secs){
  const days=Math.floor(secs/86400), hrs=Math.floor((secs%86400)/3600),
        mins=Math.floor((secs%3600)/60), s=secs%60;
  let r='';
  if(days>0) r+=days+'d ';
  r+=hrs+'h '+mins+'m '+s+'s';
  return r;
}
function moSetBar(id, pct){
  const el=document.getElementById(id);
  if(!el) return;
  const c=moBarColor(pct);
  el.className='mo-bar-fill '+c;
  el.style.width=Math.min(pct,100)+'%';
}
async function moRefreshStats(){
  const btn=document.getElementById('mo-refresh-btn');
  if(btn) btn.classList.add('spinning');
  try{
    const r=await fetch('/api/stats'); const d=await r.json();
    if(!d.success) return;
    /* CPU */
    const cpu=d.cpu.percent;
    document.getElementById('mo-cpu-val').textContent=cpu.toFixed(1);
    moSetBar('mo-cpu-bar', cpu);
    document.getElementById('mo-cpu-sub').textContent='استخدام '+cpu.toFixed(1)+'% من المعالج';
    /* RAM */
    const mem=d.memory;
    document.getElementById('mo-mem-val').textContent=mem.used_mb.toFixed(0)+' MiB';
    moSetBar('mo-mem-bar', mem.percent);
    document.getElementById('mo-mem-sub').textContent=mem.used_gb.toFixed(2)+' / '+mem.total_gb.toFixed(1)+' GiB ('+mem.percent.toFixed(1)+'%)';
    /* Disk */
    const disk=d.disk;
    document.getElementById('mo-disk-val').textContent=disk.used_gb.toFixed(1)+' GiB';
    moSetBar('mo-disk-bar', disk.percent);
    document.getElementById('mo-disk-sub').textContent=disk.used_gb.toFixed(1)+' / '+disk.total_gb.toFixed(0)+' GiB ('+disk.percent.toFixed(1)+'%)';
    /* IP & Host */
    document.getElementById('mo-ip-val').textContent=d.public_ip||'—';
    document.getElementById('mo-host-sub').textContent='hostname: '+(d.hostname||'—');
    document.getElementById('mo-hostname-val').textContent=d.hostname||'—';
    /* Uptime */
    document.getElementById('mo-uptime-val').textContent=moFmtUptime(d.uptime||0);
    /* Network */
    document.getElementById('mo-netin-val').textContent=(d.network.in_kb||0).toFixed(1)+' KiB';
    document.getElementById('mo-netout-val').textContent=(d.network.out_kb||0).toFixed(1)+' KiB';
    /* legacy hidden spans */
    document.getElementById('s-ip').textContent=d.public_ip||'';
    document.getElementById('s-host').textContent=d.hostname||'';
    document.getElementById('s-uptime').textContent=moFmtUptime(d.uptime||0);
    document.getElementById('s-cpu').textContent=cpu.toFixed(2)+'%';
    document.getElementById('s-mem').textContent=mem.used_mb.toFixed(1)+' MiB';
    document.getElementById('s-disk').textContent=disk.used_gb.toFixed(2)+' GiB';
    document.getElementById('s-in').textContent=(d.network.in_kb||0).toFixed(2)+' KiB';
    document.getElementById('s-out').textContent=(d.network.out_kb||0).toFixed(2)+' KiB';
  }catch(e){ console.error("Stats error:", e); }
  finally{ if(btn) setTimeout(()=>btn.classList.remove('spinning'),600); }
}
async function loadStats(){
  try{
    const r=await fetch('/api/system'); const d=await r.json();
    document.getElementById('s-ip').textContent = d.public_ip || 'Loading...';
    document.getElementById('s-addr').innerHTML = (d.hostname||'localhost')+':'+''' + str(MASTER_CONFIG.get('port', 20048)) + r''';
    const up = Math.floor(d.uptime || 0);
    document.getElementById('s-uptime').textContent = moFmtUptime(up);
    document.getElementById('s-cpu').innerHTML = (d.cpu_percent||0).toFixed(2)+'% <span class="max">/ 100%</span>';
    document.getElementById('s-mem').innerHTML = (d.memory_used_mb||0).toFixed(1)+' MiB <span class="max">/ '+(d.memory_total_mb||0).toFixed(0)+' MiB</span>';
    document.getElementById('s-disk').innerHTML = (d.disk_used_gb||0).toFixed(2)+' GiB <span class="max">/ '+(d.disk_total_gb||0).toFixed(0)+' GiB</span>';
    document.getElementById('s-in').textContent = (d.net_in_kb||0).toFixed(2)+' KiB';
    document.getElementById('s-out').textContent = (d.net_out_kb||0).toFixed(2)+' KiB';
    document.getElementById('s-host').textContent = d.hostname||'-';
  }catch(e){ console.error("Stats update error:", e); }
  moRefreshStats();
}
setInterval(()=>{ loadStats(); moRefreshStats(); }, 5000);
loadStats();

let consolePid = null;
let consoleSSE = null;
function setPowerState(running){
  const st=document.getElementById('power-start'), rr=document.getElementById('power-restart'), sp=document.getElementById('power-stop');
  if(!st||!rr||!sp) return;
  st.disabled=!!running; rr.disabled=!running; sp.disabled=!running;
}
setPowerState(false);

function appendConsole(t){
  const c=document.getElementById('console-output');
  const parts=String(t??'').replace(/\r/g,'').split('\n');
  parts.forEach(part=>{
    if(part==='') return;
    const safe=escapeHtml(part);
    const line=safe.replace(/^(container@pterodactyl~|\[Pterodactyl Daemon\]:)/, '<span class="console-prefix">$1</span>');
    c.insertAdjacentHTML('beforeend','<span class="console-line console-output">'+line+'</span>');
  });
  c.scrollTop = c.scrollHeight;
}

async function powerAction(a){
  if(a==='start'){
    if(consolePid){ appendConsole('[!] Already running. Stop it first.'); return; }
    const mfr = await fetch('/api/files/main-file');
    const mfd = await mfr.json();
    const fname = (mfd.success && mfd.main_file) ? mfd.main_file : null;
    if(!fname){ appendConsole('[!] No main file set. Go to Startup tab and set your main file.'); return; }
    setPowerState(true);
    document.getElementById('console-output').textContent = '';
    const r = await fetch('/api/file/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:USER_PATH, filename:fname})});
    const d = await r.json();
    if(!d.success){ setPowerState(false); appendConsole('[ERR] ' + (d.error||'Failed to start')); return; }
    consolePid = d.process_id;
    if(consoleSSE){ consoleSSE.close(); }
    const sse = new EventSource('/api/file/stream/' + consolePid);
    consoleSSE = sse;
    sse.onmessage = (e) => {
      try{
        const data = JSON.parse(e.data);
        if(data.done){ sse.close(); consoleSSE=null; consolePid=null; setPowerState(false); appendConsole('[*] Process exited.'); return; }
        if(data.line !== undefined) appendConsole(data.line);
      }catch(err){}
    };
    sse.onerror = () => { sse.close(); consoleSSE=null; };
  }
  else if(a==='restart'){
    await powerAction('stop');
    setTimeout(()=>powerAction('start'), 800);
  }
  else if(a==='stop'){
    if(!consolePid){ appendConsole('[!] Nothing is running.'); return; }
    await fetch('/api/file/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_id:consolePid})});
    if(consoleSSE){ consoleSSE.close(); consoleSSE=null; }
    appendConsole('[*] Stopped.');
    consolePid=null; setPowerState(false);
  }
}

async function runCmd(){
  const f=document.getElementById('cmd-field');
  const c=f.value.trim(); if(!c) return;
  appendConsole('» '+c);
  f.value='';
  try{
    const r=await fetch('/api/exec',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:c})});
    const d=await r.json();
    if(d.success) appendConsole(d.output||'(no output)');
    else appendConsole('[ERR] '+(d.error||''));
  }catch(e){ appendConsole('[ERR] '+e); }
}

/* =========== FILES =========== */
async function loadFiles(){
  try{
    const r=await fetch('/api/files?path='+encodeURIComponent(currentPath));
    const d=await r.json();
    const list=document.getElementById('file-list');
    document.getElementById('breadcrumb').innerHTML = renderCrumb(currentPath);
    list.innerHTML = '';
    if(currentPath !== USER_PATH){
      list.innerHTML += '<div class="file-row" onclick="goUp()"><span class="ico"><i class="fas fa-arrow-left"></i></span><span class="name">..</span></div>';
    }
    (d.files||[]).forEach(f=>{
      const ico = f.is_dir ? '<i class="fas fa-folder"></i>' : '<i class="fas fa-file-alt"></i>';
      const safe = f.name.replace(/'/g,"\\'").replace(/"/g,'&quot;');
      const fp = (currentPath+'/'+f.name).replace(/\/\//g,'/');
      list.innerHTML += `
        <div class="file-row" style="gap:6px" onclick="selectFileRow(this)">
          <span class="chk" onclick="toggleFileSelection(event,this)"></span>
          <span class="ico">${ico}</span>
          <span class="name" style="cursor:pointer" onclick="event.stopPropagation();${f.is_dir?`enterDir('${safe}')`:`(/\.(zip|tar|gz|rar|7z|png|jpg|jpeg|gif|webp)$/i.test('${safe}')?toast('This file is not editable. Use the … menu.'):openEdit('${safe}'))`}">${escapeHtml(f.name)}</span>
          <span class="menu" title="More" onclick="event.stopPropagation();fileMenu('${safe}','${f.is_dir}',this)"><i class="fas fa-ellipsis-h"></i></span>
        </div>`;
    });
  }catch(e){ toast('Failed to load files',true); }
}
function selectFileRow(row){
  document.querySelectorAll('#file-list .file-row.selected').forEach(x=>x.classList.remove('selected'));
  if(row) row.classList.add('selected');
}
function toggleFileSelection(ev, chk){
  ev.stopPropagation();
  const row=chk.closest('.file-row');
  if(row) row.classList.toggle('selected');
}
function selectAllFiles(){
  const rows=[...document.querySelectorAll('#file-list .file-row')].filter(x=>!x.querySelector('.fa-arrow-left'));
  const all=rows.length && rows.every(x=>x.classList.contains('selected'));
  rows.forEach(x=>x.classList.toggle('selected',!all));
  toast(all?'Selection cleared':'All files selected');
}
function clearFileSelection(){
  document.querySelectorAll('#file-list .file-row.selected').forEach(x=>x.classList.remove('selected'));
  toast('Selection cleared');
}
async function deleteSelectedFiles(){
  const names=[...document.querySelectorAll('#file-list .file-row.selected .name')].map(x=>x.textContent.trim()).filter(x=>x && x!=='..');
  if(!names.length){toast('Select one or more files first',true);return;}
  if(!confirm('Delete '+names.length+' selected item(s)?')) return;
  const r=await fetch('/api/files/delete-many',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentPath,names})});
  const d=await r.json(); if(d.success){toast('Deleted '+d.deleted+' item(s)');loadFiles();}else toast(d.error||'Delete failed',true);
}
async function archiveSelected(singleName){
  const rows=[...document.querySelectorAll('#file-list .file-row.selected')];
  let names=rows.map(row=>row.querySelector('.name')?.textContent?.trim()).filter(Boolean);
  if(singleName && !names.includes(singleName)) names=[singleName];
  if(!names.length){ toast('Select one or more files first',true); return; }
  const suggested=names.length===1?names[0].replace(/\.[^.]+$/,'')+'.zip':'archive.zip';
  const archiveName=prompt('Archive name:',suggested);
  if(!archiveName) return;
  const r=await fetch('/api/files/archive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentPath,names,archive_name:archiveName})});
  const d=await r.json(); if(d.success){toast('Archive created: '+d.archive);loadFiles();}else toast(d.error||'Archive failed',true);
}
async function moveFile(name, isDir){
  const dest=prompt('Destination folder (relative to current folder):','');
  if(dest===null) return;
  const target=(currentPath.replace(/\/$/,'')+'/'+(dest.trim()||'.')).replace(/\/\//g,'/');
  const r=await fetch('/api/files/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old_path:currentPath.replace(/\/$/,'')+'/'+name,dest_dir:target})});
  const d=await r.json(); if(d.success){toast('Moved');loadFiles();}else toast(d.error||'Move failed',true);
}
async function deleteFile(name, isDir){
  if(!confirm('Delete '+name+'?')) return;
  const fp = currentPath.replace(/\/$/,'')+'/'+name;
  const r=await fetch('/api/files/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:fp})});
  const d=await r.json(); if(d.success){toast('Deleted');loadFiles();}else toast('Failed',true);
}
async function renameFile(name, isDir){
  const nn = prompt('الاسم الجديد:', name);
  if(!nn || nn===name || nn.includes('/') || nn.includes('..')) return;
  const fp = currentPath.replace(/\/$/,'')+'/'+name;
  const r=await fetch('/api/files/rename',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({old_path:fp, new_name:nn})});
  const d=await r.json();
  if(d.success){toast('تمت إعادة التسمية'); loadFiles();}
  else toast(d.error||'فشل',true);
}
async function setMainFile(name){
  const r=await fetch('/api/files/set-main',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:name,path:currentPath})});
  const d=await r.json();
  if(d.success){toast('<i class="fas fa-check-circle" style="color:#2ecc71"></i> Set as main: '+name);}else toast('Failed',true);
}
function renderCrumb(p){
  const parts = p.split('/').filter(Boolean);
  let acc='';
  let html='<span class="crumb sep">/</span>';
  parts.forEach((seg,i)=>{
    acc += '/'+seg;
    html += `<span class="crumb" onclick="navTo('${acc}')">${seg}</span><span class="sep">/</span>`;
  });
  return html;
}
function navTo(p){ currentPath=p; loadFiles(); }
function enterDir(name){ currentPath = currentPath.replace(/\/$/,'')+'/'+name; loadFiles(); }
function goUp(){
  const p = currentPath.replace(/\/$/,'').split('/'); p.pop();
  currentPath = p.join('/') || '/';
  if(!currentPath.startsWith(USER_PATH) && !IS_MASTER) currentPath = USER_PATH;
  loadFiles();
}
async function createDir(){
  const n = prompt('Directory name:'); if(!n) return;
  const r=await fetch('/api/files/folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path: currentPath+'/'+n})});
  const d=await r.json(); if(d.success){toast('Created');loadFiles();}else toast('Failed',true);
}
async function newFile(){
  const n = prompt('File name (e.g. app.py):'); if(!n) return;
  const r=await fetch('/api/files/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path: currentPath+'/'+n,content:''})});
  const d=await r.json(); if(d.success){toast('Created');loadFiles();}else toast('Failed',true);
}
async function uploadFile(inp){
  const f=inp.files[0]; if(!f) return;
  const fd=new FormData(); fd.append('file',f); fd.append('path',currentPath);
  const r=await fetch('/api/files/upload',{method:'POST',body:fd});
  const d=await r.json(); if(d.success){toast('Uploaded');loadFiles();}else toast('Failed',true);
  inp.value='';
}
function closeFileMenu(){ document.querySelectorAll('.file-action-menu').forEach(x=>x.remove()); document.querySelectorAll('.file-row.menu-open').forEach(x=>x.classList.remove('menu-open')); }
async function fileMenu(name, isDir, trigger){
  closeFileMenu();
  const row=trigger && trigger.closest('.file-row'); if(row) row.classList.add('menu-open');
  const menu=document.createElement('div'); menu.className='file-action-menu';
  const actions=[['fa-pencil','Rename',()=>renameFile(name,isDir)],['fa-turn-up','Move',()=>moveFile(name,isDir)],['fa-file-code','Permissions',()=>toast('Permissions: managed by the isolated runner')],['fa-copy','Copy',()=>toast('Copy: select a destination in the file manager')],['fa-file-zipper','Archive',()=>archiveSelected(name)],['fa-file-arrow-down','Download',()=>{window.open('/api/files/download?path='+encodeURIComponent(currentPath+'/'+name),'_blank')}],['fa-trash-can','Delete',()=>deleteFile(name,isDir)]];
  actions.forEach(([icon,label,fn])=>{const b=document.createElement('button');b.innerHTML='<i class="fas '+icon+'"></i>'+label;b.onclick=()=>{closeFileMenu();fn()};menu.appendChild(b)});
  document.body.appendChild(menu); const r=trigger.getBoundingClientRect(); menu.style.left=Math.max(8,r.right-186)+'px'; menu.style.top=Math.min(window.innerHeight-menu.offsetHeight-8,r.bottom+4)+'px';
  setTimeout(()=>document.addEventListener('click',closeFileMenu,{once:true}),0);
}
async function openEdit(name){
  const fp = currentPath+'/'+name;
  const r=await fetch('/api/files/content?path='+encodeURIComponent(fp));
  const d=await r.json();
  if(d.content===undefined){ toast('Cannot read',true); return; }
  currentEditPath = fp;
  document.getElementById('edit-title').textContent = 'Edit: '+name;
  document.getElementById('edit-breadcrumb').textContent = currentPath.replace(USER_PATH, '/home/container') + '/' + name;
  const ext=(name.split('.').pop()||'').toLowerCase();
  const langMap={js:'JavaScript',mjs:'JavaScript',cjs:'JavaScript',json:'JSON',lua:'Lua',md:'Markdown',py:'Python',txt:'Plain Text'};
  const lang=document.getElementById('edit-language');
  if(lang && langMap[ext]) lang.value=langMap[ext];
  document.getElementById('edit-content').value = d.content;
  document.getElementById('edit-modal').classList.add('show');
}
async function saveEdit(){
  const c = document.getElementById('edit-content').value;
  const r=await fetch('/api/files/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentEditPath,content:c})});
  const d=await r.json(); if(d.success){toast('Saved');closeModal('edit-modal');}else toast('Failed',true);
}
function runCurrentFile(){
  if(!currentEditPath) return;
  const name = currentEditPath.split('/').pop();
  closeModal('edit-modal');
  runFile(name);
}
let runSSE = null;
async function runFile(name){
  const r=await fetch('/api/file/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:currentPath, filename:name})});
  const d=await r.json();
  if(!d.success){ toast(d.error||'Failed to run',true); return; }
  currentRunPid = d.process_id;
  const out = document.getElementById('run-output');
  out.textContent = '';
  document.getElementById('run-modal').classList.add('show');
  if(runPoll){ clearInterval(runPoll); runPoll=null; }
  if(runSSE){ runSSE.close(); runSSE=null; }
  const sse = new EventSource('/api/file/stream/'+currentRunPid);
  runSSE = sse;
  sse.onmessage = (e) => {
    try{
      const data = JSON.parse(e.data);
      if(data.done){ sse.close(); runSSE=null; appendRunLine('[*] Process finished.'); return; }
      if(data.line !== undefined) appendRunLine(data.line);
    }catch(err){}
  };
  sse.onerror = () => { sse.close(); runSSE=null; };
}
function appendRunLine(line){
  const c = document.getElementById('run-output');
  c.textContent += line + '\n';
  c.scrollTop = c.scrollHeight;
}
async function pollRunOutput(){
  if(!currentRunPid) return;
  const r=await fetch('/api/file/output/'+currentRunPid);
  const d=await r.json();
  if(d.success){
    const c=document.getElementById('run-output'); c.scrollTop=c.scrollHeight;
    if(!d.is_running){ clearInterval(runPoll); runPoll=null; }
  }
}
async function sendRunInput(){
  const f=document.getElementById('run-input'); const v=f.value;
  if(!v||!currentRunPid) return; f.value='';
  await fetch('/api/file/input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_id:currentRunPid,input:v})});
}
async function stopRun(){
  if(!currentRunPid) return;
  await fetch('/api/file/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({process_id:currentRunPid})});
  toast('Stopped');
  closeRun();
}
function closeRun(){
  document.getElementById('run-modal').classList.remove('show');
  if(runPoll){ clearInterval(runPoll); runPoll=null; }
  if(runSSE){ runSSE.close(); runSSE=null; }
  currentRunPid=null;
}
function closeModal(id){ document.getElementById(id).classList.remove('show'); }

/* =========== ACTIVITY =========== */
async function loadActivity(){
  try{
    const r=await fetch('/api/activity'); const d=await r.json();
    const list = document.getElementById('activity-list');
    list.innerHTML = '';
    (d.events||[]).forEach(e=>{
      list.innerHTML += `
        <div class="activity-card">
          <div class="a-head"><span class="user">${escapeHtml(e.username||'-')}</span> — <span class="action">${escapeHtml(e.action||'')}</span></div>
          ${e.details?`<div class="a-desc">${escapeHtml(e.details)}</div>`:''}
          <div class="a-meta">${escapeHtml(e.ip||'-')} | ${escapeHtml(e.time_text||'')}</div>
        </div>`;
    });
    if(!(d.events||[]).length) list.innerHTML = '<div class="activity-card"><div class="a-desc">No activity yet.</div></div>';
  }catch(e){ toast('Failed',true); }
}
function escapeHtml(s){ return (s||'').toString().replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

/* =========== SETTINGS =========== */
async function loadSettings(){
  try{
    const r=await fetch('/api/system'); const d=await r.json();
    const port = ''' + str(MASTER_CONFIG.get('port', 3177)) + r''';
    document.getElementById('sftp-addr').value = 'sftp://'+(d.hostname||'localhost')+':2022';
    document.getElementById('sftp-user').value = ''' + json.dumps(MASTER_USERNAME if is_master else 'user') + r''';
    document.getElementById('dbg-node').value = d.hostname || 'Local Node';
    document.getElementById('dbg-id').value = ''' + json.dumps(str(uuid.uuid4())) + r''';
    document.getElementById('dbg-plat').value = d.platform || '-';
    if(IS_MASTER){
      const mp=document.getElementById('m-port'); if(mp) mp.value = port;
    }
    document.getElementById('primary-host').textContent = (d.hostname||'localhost');
  }catch(e){}
}
async function changeUser(){
  const v=document.getElementById('m-newuser').value.trim(); if(!v) return;
  const r=await fetch('/api/master/change-username',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_username:v})});
  const d=await r.json(); toast(d.success?'Saved (re-login)':'Failed', !d.success);
}
async function changePass(){
  const cur=document.getElementById('m-curpass').value; const nw=document.getElementById('m-newpass').value;
  if(!cur||!nw) return;
  const r=await fetch('/api/master/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:cur,new_password:nw})});
  const d=await r.json(); toast(d.success?'Password changed':'Wrong current password', !d.success);
}
async function changePort(){
  const p=parseInt(document.getElementById('m-port').value); if(!p) return;
  if(!confirm('Change port and restart panel?')) return;
  await fetch('/api/master/change-port',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:p})});
  toast('Restarting...');
}
async function restartPanel(){
  if(!confirm('Restart panel?')) return;
  await fetch('/api/master/restart',{method:'POST'}); toast('Restarting...');
}
async function sysAction(a){
  const r=await fetch('/api/system/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})});
  const d=await r.json(); toast(d.success?('OK: '+a):'Failed', !d.success);
}
async function clearLogs(){
  await fetch('/api/logs/clear',{method:'POST'}); toast('Logs cleared');
}

/* =========== USER SETTINGS (regular users) =========== */
async function loadUserSettings(){
  if(IS_MASTER) return;
  try{
    const r = await fetch('/api/user/settings');
    const d = await r.json();
    if(d.success){
      const rt = document.getElementById('u-runtime');
      if(rt){ rt.value = d.runtime||'python'; updateRuntimeVersions(); }
      const ver = document.getElementById('u-runtime-ver');
      if(ver) ver.value = d.version||'3.11';
      const mf = document.getElementById('u-main-file');
      if(mf) mf.value = d.main_file||'main.py';
    }
  }catch(e){}
}
function updateRuntimeVersions(){
  const rt = document.getElementById('u-runtime');
  if(!rt) return;
  const ver = document.getElementById('u-runtime-ver');
  if(!ver) return;
  const cur = ver.value;
  if(rt.value==='python'){
    ver.innerHTML='<option value="3.11">3.11 (default)</option><option value="3.12">3.12</option><option value="3.10">3.10</option><option value="3.9">3.9</option>';
  } else {
    ver.innerHTML='<option value="20">20 LTS (default)</option><option value="22">22</option><option value="18">18</option><option value="16">16</option>';
  }
}
async function saveUserSettings(){
  const runtime = document.getElementById('u-runtime').value;
  const version = document.getElementById('u-runtime-ver').value;
  const mainFile = (document.getElementById('u-main-file').value||'').trim();
  if(!mainFile){ toast('Main file cannot be empty',true); return; }
  const r = await fetch('/api/user/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({runtime,version,main_file:mainFile})});
  const d = await r.json();
  toast(d.success?'✅ Settings saved':(d.error||'Failed'),!d.success);
}
async function changeUserPass(){
  const cur = document.getElementById('u-curpass').value;
  const nw  = document.getElementById('u-newpass').value;
  const cn  = document.getElementById('u-conpass').value;
  if(!cur||!nw||!cn){ toast('Fill all fields',true); return; }
  if(nw!==cn){ toast('Passwords do not match',true); return; }
  if(nw.length<6){ toast('Password too short (min 6)',true); return; }
  const r = await fetch('/api/user/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:cur,new_password:nw})});
  const d = await r.json();
  if(d.success){
    toast('✅ Password changed');
    ['u-curpass','u-newpass','u-conpass'].forEach(id=>{ const el=document.getElementById(id); if(el) el.value=''; });
  } else toast(d.error||'Wrong current password',true);
}
async function deleteMyServer(){
  const pass = document.getElementById('u-del-pass').value;
  if(!pass){ toast('Enter your password',true); return; }
  if(!confirm('⚠️ Delete your server permanently? All files and data will be lost. This cannot be undone.')) return;
  const r = await fetch('/api/user/delete-account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pass})});
  const d = await r.json();
  if(d.success){ toast('Server deleted. Redirecting...'); setTimeout(()=>window.location.href='/logout',2000); }
  else toast(d.error||'Failed',true);
}

/* =========== USERS =========== */
async function loadUsers(){
  if(!IS_MASTER) return;
  const r=await fetch('/api/users/list'); const d=await r.json();
  const list=document.getElementById('user-list'); list.innerHTML='';
  (d.users||[]).forEach(u=>{
    list.innerHTML += `
      <div class="user-row" style="flex-wrap:wrap;gap:8px">
        <div style="flex:1;min-width:160px">
          <div class="uname">${escapeHtml(u.username)}</div>
          <div class="meta">Sessions: ${u.active_sessions||0}/${u.max_sessions||1} &nbsp;|&nbsp; Servers: ${u.max_servers||1} &nbsp;|&nbsp; Server: ${escapeHtml(u.server_name||'')} &nbsp;|&nbsp; Main: ${escapeHtml(u.main_file||'main.py')}</div>
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn-action gray" style="padding:8px 14px;font-size:12px" onclick="openEditUser('${escapeHtml(u.username)}',${u.max_sessions||1},${u.max_servers||1},'${escapeHtml(u.main_file||'main.py')}','${escapeHtml(u.server_name||'')}')"><i class="fas fa-pen"></i> Edit</button>
          <button class="btn-action danger" style="padding:8px 14px;font-size:12px" onclick="delUser('${escapeHtml(u.username)}')">Delete</button>
        </div>
      </div>`;
  });
}
function openEditUser(uname, maxSess, maxSrv, mainFile, serverName){
  document.getElementById('eu-name').value=uname;
  document.getElementById('eu-pass').value='';
  document.getElementById('eu-max').value=maxSess;
  const srv=document.getElementById('eu-maxsrv');
  if(srv){ Array.from(srv.options).forEach(o=>{ o.selected=(parseInt(o.value)===parseInt(maxSrv)); }); }
  document.getElementById('eu-server-name').value=serverName||'';
  document.getElementById('eu-main').value=mainFile||'main.py';
  document.getElementById('edit-user-modal').classList.add('show');
}
async function saveEditUser(){
  const uname=document.getElementById('eu-name').value;
  const pass=document.getElementById('eu-pass').value;
  const maxSess=document.getElementById('eu-max').value;
  const maxSrv=document.getElementById('eu-maxsrv').value;
  const mainFile=document.getElementById('eu-main').value.trim()||'main.py';
  const serverName=document.getElementById('eu-server-name').value.trim();
  const body={username:uname,max_sessions:maxSess,max_servers:maxSrv,main_file:mainFile,server_name:serverName};
  if(pass) body.password=pass;
  const r=await fetch('/api/users/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.success){toast('User updated');closeModal('edit-user-modal');loadUsers();}else toast('Failed',true);
}
async function addUser(){
  const u=document.getElementById('u-name').value.trim();
  const p=document.getElementById('u-pass').value;
  const m=document.getElementById('u-max').value||1;
  const ms=document.getElementById('u-maxsrv')?document.getElementById('u-maxsrv').value:1;
  const mf=document.getElementById('u-main')?document.getElementById('u-main').value.trim()||'main.py':'main.py';
  const sn=document.getElementById('u-server-name')?document.getElementById('u-server-name').value.trim()||'':'';
  if(!u||!p){ toast('Fill all fields',true); return; }
  const r=await fetch('/api/users/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p,max_sessions:m,max_servers:ms,main_file:mf,server_name:sn})});
  const d=await r.json(); if(d.success){toast('User added');loadUsers();}else toast('Failed',true);
}
async function delUser(u){
  if(!confirm('Delete user '+u+'?')) return;
  await fetch('/api/users/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u})});
  toast('Deleted'); loadUsers();
}

/* =========== BACKUPS =========== */
async function loadBackups(){
  if(!IS_MASTER) return;
  const r=await fetch('/api/backups/list'); const d=await r.json();
  const list=document.getElementById('backup-list'); list.innerHTML='';
  (d.backups||[]).forEach(b=>{
    list.innerHTML += `<div class="user-row"><div><div class="uname">${escapeHtml(b.name)}</div><div class="meta">${b.size}</div></div></div>`;
  });
  if(!(d.backups||[]).length) list.innerHTML='<div class="activity-card"><div class="a-desc">No backups yet.</div></div>';
}
async function createBackup(){
  toast('Creating backup...');
  const r=await fetch('/api/backups/create',{method:'POST'});
  const d=await r.json(); toast(d.success?'Backup created':'Failed', !d.success);
  loadBackups();
}

/* =========== SCHEDULES =========== */
async function loadSchedules(){
  try{
    const r=await fetch('/api/schedules/list'); const d=await r.json();
    const list=document.getElementById('sch-list'); list.innerHTML='';
    (d.schedules||[]).forEach(s=>{
      list.innerHTML += `<div class="user-row"><div><div class="uname">${escapeHtml(s.name)}</div><div class="meta">${escapeHtml(s.command)} — ${escapeHtml(s.schedule)}</div></div></div>`;
    });
  }catch(e){}
}
async function addSchedule(){
  const n=document.getElementById('sch-name').value.trim();
  const c=document.getElementById('sch-cmd').value.trim();
  const cr=document.getElementById('sch-cron').value.trim()||'* * * * *';
  if(!n||!c){ toast('Fill all fields',true); return; }
  const r=await fetch('/api/schedules/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,command:c,schedule:cr})});
  const d=await r.json(); if(d.success){toast('Added');loadSchedules();}else toast('Failed',true);
}

/* =========== PORTS / NETWORK =========== */
async function loadPorts(){
  if(!IS_MASTER) return;
  const r=await fetch('/api/ports/list'); const d=await r.json();
  const list=document.getElementById('port-list'); if(!list) return; list.innerHTML='';
  (d.ports||[]).forEach(p=>{
    list.innerHTML += `
      <div class="port-card">
        <div class="port-head">
          <div class="port-host">${escapeHtml(p.note||'Port')}</div>
          <div class="port-badge">${p.port}</div>
        </div>
        <div class="port-note">Status: ${p.status||'idle'}</div>
        <div class="row-end" style="gap:6px;margin-top:8px">
          <button class="btn-action danger" onclick="delPort(${p.port})">Remove</button>
        </div>
      </div>`;
  });
}
async function addPort(){
  const p=parseInt(document.getElementById('new-port').value);
  const n=document.getElementById('new-port-note').value||'Custom port';
  if(!p){ toast('Invalid port',true); return; }
  const r=await fetch('/api/ports/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:p,note:n})});
  const d=await r.json(); if(d.success){toast('Added');loadPorts();}else toast(d.error||'Failed',true);
}
async function delPort(p){
  if(!confirm('Remove port '+p+'?')) return;
  await fetch('/api/ports/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port:p})});
  toast('Removed'); loadPorts();
}
async function scanPorts(){
  const h=document.getElementById('scan-host').value;
  const ps=document.getElementById('scan-ports').value.split(',').map(x=>x.trim()).filter(Boolean);
  const r=await fetch('/api/network/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({host:h,ports:ps})});
  const d=await r.json();
  document.getElementById('scan-out').innerHTML = (d.results||[]).map(x=>`Port ${x.port}: <span style="color:${x.open?'#65c466':'#e53935'}">${x.open?'OPEN':'CLOSED'}</span>`).join('<br>');
}

/* =========== STARTUP / MAIN FILE =========== */
async function loadMainFile(){
  try{
    const r=await fetch('/api/files/main-file'); const d=await r.json();
    if(d.success && d.main_file){
      const el=document.getElementById('startup-cmd');
      if(el) el.value=d.main_file;
    }
  }catch(e){}
}
async function runMainFile(){
  const mf=document.getElementById('startup-cmd');
  if(!mf||!mf.value.trim()){ toast('No main file set',true); return; }
  const fname=mf.value.trim();
  const r=await fetch('/api/file/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:USER_PATH, filename:fname})});
  const d=await r.json();
  if(!d.success){ toast(d.error||'Failed to run',true); return; }
  currentRunPid = d.process_id;
  const out = document.getElementById('run-output');
  out.textContent = '';
  document.getElementById('run-modal').classList.add('show');
  if(runPoll){ clearInterval(runPoll); runPoll=null; }
  if(runSSE){ runSSE.close(); runSSE=null; }
  const sse = new EventSource('/api/file/stream/'+currentRunPid);
  runSSE = sse;
  sse.onmessage = (e) => {
    try{
      const data = JSON.parse(e.data);
      if(data.done){ sse.close(); runSSE=null; appendRunLine('[*] Process finished.'); return; }
      if(data.line !== undefined) appendRunLine(data.line);
    }catch(err){}
  };
  sse.onerror = () => { sse.close(); runSSE=null; };
  toast('Running: '+fname);
}

/* =========== PIP =========== */
async function installPip(){
  const p=document.getElementById('pip-pkg').value.trim(); if(!p) return;
  toast('Installing '+p+'...');
  const r=await fetch('/api/packages/install/pip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({package:p})});
  const d=await r.json(); toast(d.success?'Installed':'Failed', !d.success);
}

/* =========== SEARCH =========== */
function loadSearch(){
  const q=prompt('Search (placeholder):'); if(q) toast('Search: '+q);
}

/* =========== DB (simple) =========== */
async function createDB(){
  const n=document.getElementById('db-name').value.trim(); if(!n) return;
  const r=await fetch('/api/files/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:USER_PATH+'/'+n+'.json',content:'{}'})});
  const d=await r.json(); toast(d.success?'DB created':'Failed', !d.success);
}

/* init */
loadFiles();

/* =========== OWNER PANEL JS =========== */
async function loadOwnerPanel(){
  if(!IS_MASTER) return;
  try{
    const [statsR, usersR, maintR, ownerR] = await Promise.all([
      fetch('/api/owner/stats'),
      fetch('/api/users/list'),
      fetch('/api/owner/maintenance'),
      fetch('/api/owner/config')
    ]);
    if(!statsR.ok || !usersR.ok || !maintR.ok || !ownerR.ok){
      if(statsR.status===403||usersR.status===403||maintR.status===403||ownerR.status===403){
        toast('غير مصرح للوصول إلى لوحة المالك', true); return;
      }
    }
    const stats = await statsR.json();
    const usersData = await usersR.json();
    const maint = await maintR.json();
    const ownerCfg = await ownerR.json();

    // --- Stats ---
    const userList = usersData.users||[];
    const bannedCount = userList.filter(u=>u.banned).length;
    const onlineCount = userList.filter(u=>(u.active_sessions||0)>0).length;
    document.getElementById('ow-users').textContent = userList.length;
    document.getElementById('ow-sessions').textContent = onlineCount;
    document.getElementById('ow-banned').textContent = bannedCount;
    document.getElementById('ow-servers').textContent = stats.total_servers||0;
    document.getElementById('ow-bots').textContent = stats.active_bots||0;
    document.getElementById('ow-zips').textContent = stats.zip_files||0;

    // --- Online Users ---
    const sessList = document.getElementById('ow-sessions-list');
    if(sessList){
      const online = userList.filter(u=>(u.active_sessions||0)>0);
      if(!online.length){
        sessList.innerHTML = '<div style="color:#9aa9b3;font-size:13px;padding:6px 0">No users online right now.</div>';
      } else {
        sessList.innerHTML = online.map(u=>`
          <div class="session-row">
            <div>
              <div class="s-user"><i class="fas fa-circle" style="font-size:8px;color:#2ecc71;margin-right:5px"></i>${escapeHtml(u.username)}</div>
              <div class="s-meta">${u.active_sessions||0} session(s) active &nbsp;|&nbsp; Servers: ${u.max_servers||1}</div>
            </div>
            <button class="owner-action-btn ban" onclick="ownerKickUser('${escapeHtml(u.username)}')"><i class="fas fa-sign-out-alt"></i> Kick</button>
          </div>`).join('');
      }
    }

    // --- User Table ---
    const tbody = document.getElementById('ow-user-tbody');
    if(tbody){
      if(!userList.length){
        tbody.innerHTML = '<tr><td colspan="6" style="color:#9aa9b3;padding:14px">No users yet.</td></tr>';
      } else {
        tbody.innerHTML = userList.map(u=>{
          const isBanned = u.banned||false;
          const isOnline = (u.active_sessions||0)>0;
          const badge = isBanned
            ? '<span class="u-badge banned">Banned</span>'
            : (isOnline ? '<span class="u-badge online">Online</span>' : '<span class="u-badge offline">Offline</span>');
          const banBtn = isBanned
            ? `<button class="owner-action-btn unban" onclick="ownerSetBan('${escapeHtml(u.username)}',false)"><i class="fas fa-unlock"></i> Unban</button>`
            : `<button class="owner-action-btn ban" onclick="ownerSetBan('${escapeHtml(u.username)}',true)"><i class="fas fa-ban"></i> Ban</button>`;
          return `<tr>
            <td style="color:#c8d4dc;font-weight:600">${escapeHtml(u.username)}</td>
            <td>${badge}</td>
            <td style="color:#9aa9b3">${u.active_sessions||0}/${u.max_sessions||'∞'}</td>
            <td style="color:#9aa9b3">${u.max_servers||1}</td>
            <td style="color:#7a8c98;font-family:monospace;font-size:11px">${escapeHtml(u.main_file||'main.py')}</td>
            <td>
              <div style="display:flex;gap:4px;flex-wrap:wrap">
                ${banBtn}
                <button class="owner-action-btn pw" onclick="ownerResetPass('${escapeHtml(u.username)}')"><i class="fas fa-key"></i> Pass</button>
                <button class="owner-action-btn del" onclick="delUser('${escapeHtml(u.username)}')"><i class="fas fa-trash"></i></button>
              </div>
            </td>
          </tr>`;
        }).join('');
      }
    }

    // --- Maintenance ---
    const chk = document.getElementById('maint-toggle-chk');
    if(chk) chk.checked = maint.enabled||false;
    const msgEl = document.getElementById('maint-msg');
    if(msgEl) msgEl.value = maint.message||'';
    const maintBadge = document.getElementById('maint-status-badge');
    if(maintBadge){ maintBadge.style.display = maint.enabled ? 'inline-flex' : 'none'; }

    // --- Bot Status ---
    const badge = document.getElementById('bot-status-badge');
    const botPanel = document.getElementById('bot-control-panel');
    const tokenEl = document.getElementById('tg-token');
    const ownerIdEl = document.getElementById('tg-ownerid');
    const botUserBadge = document.getElementById('bot-username-badge');
    if(ownerCfg.bot_linked){
      if(badge) badge.innerHTML = '<span class="bot-linked-badge"><i class="fas fa-check-circle" style="color:#2ecc71"></i> Bot Linked & Active</span>';
      if(botPanel) botPanel.style.display='block';
      if(botUserBadge && ownerCfg.bot_username) botUserBadge.textContent = '@'+ownerCfg.bot_username;
    } else {
      if(badge) badge.innerHTML = '<span class="bot-unlinked-badge"><i class="fas fa-exclamation-triangle" style="color:#f39c12"></i> Bot Not Linked</span>';
      if(botPanel) botPanel.style.display='none';
      if(botUserBadge) botUserBadge.textContent='';
    }
    if(tokenEl && ownerCfg.telegram_token) tokenEl.placeholder = '••••• (Token saved)';
    if(ownerIdEl && ownerCfg.telegram_owner_id) ownerIdEl.value = ownerCfg.telegram_owner_id;

    // --- Panel Settings ---
    const pnEl = document.getElementById('panel-name-inp');
    const pwEl = document.getElementById('panel-welcome-inp');
    if(pnEl) pnEl.value = ownerCfg.panel_name||'';
    if(pwEl) pwEl.value = ownerCfg.welcome_msg||'';

    // --- Load rest ---
    loadOwnerZips();
    loadAnnouncements();
    loadOwnerActivityFeed();
    loadSupportTickets();

    // --- Bot Lock ---
    try{
      const botLockR = await fetch('/api/owner/bot-lock');
      if(botLockR.ok){
        const bl = await botLockR.json();
        const blChk = document.getElementById('bot-lock-chk');
        const blMsg = document.getElementById('bot-lock-msg');
        if(blChk) blChk.checked = bl.locked||false;
        if(blMsg) blMsg.value = bl.message||'البوت في وضع الصيانة مؤقتاً 🔧';
      }
    }catch(_){}

    // --- Star Payment ---
    try{
      const starR = await fetch('/api/owner/star-payment');
      if(starR.ok){
        const sp = await starR.json();
        const spEl = document.getElementById('star-price');
        const slEl = document.getElementById('star-label');
        if(spEl) spEl.value = sp.price||'1';
        if(slEl) slEl.value = sp.label||'دعم بنجمة';
      }
    }catch(_){}

    // --- Proof Channel ---
    try{
      const pcR = await fetch('/api/owner/proof-channel');
      if(pcR.ok){
        const pc = await pcR.json();
        const pcEl = document.getElementById('proof-channel');
        if(pcEl) pcEl.value = pc.channel||'';
      }
    }catch(_){}

  } catch(e){ toast('Failed to load owner panel', true); }
}

async function toggleMaintenance(){
  const chk = document.getElementById('maint-toggle-chk');
  const msg = document.getElementById('maint-msg').value;
  const r = await fetch('/api/owner/maintenance', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:chk.checked, message:msg})});
  const d = await r.json();
  const maintBadge = document.getElementById('maint-status-badge');
  if(maintBadge) maintBadge.style.display = chk.checked ? 'inline-flex' : 'none';
  toast(d.success ? (chk.checked ? '<i class="fas fa-wrench"></i> Maintenance ON' : '<i class="fas fa-check-circle" style="color:#2ecc71"></i> Maintenance OFF') : 'Failed', !d.success);
}

async function saveMaintMsg(){
  const chk = document.getElementById('maint-toggle-chk');
  const msg = document.getElementById('maint-msg').value;
  const r = await fetch('/api/owner/maintenance', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled:chk.checked, message:msg})});
  const d = await r.json();
  toast(d.success ? 'Message saved' : 'Failed', !d.success);
}

async function linkBot(){
  const token = document.getElementById('tg-token').value.trim();
  const ownerId = document.getElementById('tg-ownerid').value.trim();
  if(!token || !ownerId){ toast('Enter token and owner ID', true); return; }
  const statusEl = document.getElementById('bot-link-status');
  statusEl.textContent = '⏳ Linking bot...';
  const r = await fetch('/api/owner/bot/link', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token, owner_id:ownerId})});
  const d = await r.json();
  if(d.success){
    statusEl.innerHTML = '<i class="fas fa-check-circle" style="color:#2ecc71"></i> Bot linked: @' + escapeHtml(d.bot_username||'unknown');
    statusEl.style.color = '#65c466';
    toast('Bot linked successfully!');
    loadOwnerPanel();
  } else {
    statusEl.innerHTML = '<i class="fas fa-times-circle" style="color:#e74c3c"></i> Error: ' + escapeHtml(d.error||'Failed');
    statusEl.style.color = '#e53935';
    toast('Failed: ' + (d.error||''), true);
  }
}

async function unlinkBot(){
  if(!confirm('Unlink bot?')) return;
  const r = await fetch('/api/owner/bot/unlink', {method:'POST'});
  const d = await r.json();
  toast(d.success ? 'Bot unlinked' : 'Failed', !d.success);
  if(d.success) loadOwnerPanel();
}

async function botAction(action){
  const r = await fetch('/api/owner/bot/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action})});
  const d = await r.json();
  if(r.status===403){ toast('غير مصرح بهذه العملية', true); return; }
  const bc = document.getElementById('bot-console');
  if(bc){ bc.textContent += '[' + new Date().toLocaleTimeString() + '] ' + action + ': ' + (d.message||d.error||'done') + '\n'; bc.scrollTop=bc.scrollHeight; }
  toast(d.success ? 'Bot ' + action : 'Failed', !d.success);
}

async function sendBotCmd(){
  const inp = document.getElementById('bot-cmd-input');
  const cmd = inp.value.trim(); if(!cmd) return;
  inp.value = '';
  const r = await fetch('/api/owner/bot/cmd', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command:cmd})});
  const d = await r.json();
  if(r.status===403){ toast('غير مصرح بهذه العملية', true); return; }
  const bc = document.getElementById('bot-console');
  if(bc){ bc.textContent += '» ' + cmd + '\n' + (d.output||d.error||'') + '\n'; bc.scrollTop=bc.scrollHeight; }
}

async function refreshBotStats(){
  const r = await fetch('/api/owner/stats');
  const d = await r.json();
  document.getElementById('ow-servers').textContent = d.total_servers||0;
  document.getElementById('ow-bots').textContent = d.active_bots||0;
  document.getElementById('ow-zips').textContent = d.zip_files||0;
  toast('Stats refreshed');
}

async function loadOwnerZips(){
  try{
    const r = await fetch('/api/owner/zips');
    const d = await r.json();
    const list = document.getElementById('owner-zip-list');
    if(!list) return;
    list.innerHTML = '';
    if(!(d.zips||[]).length){ list.innerHTML = '<div style="color:#9aa9b3;font-size:13px;padding:10px">No ZIP files found.</div>'; return; }
    (d.zips||[]).forEach(z=>{
      list.innerHTML += `
        <div class="zip-item">
          <div>
            <div class="z-name"><i class="fas fa-box-open"></i> ${escapeHtml(z.name)}</div>
            <div class="z-size">${escapeHtml(z.user||'-')} • ${escapeHtml(z.size||'')}</div>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn-action gray" style="padding:6px 12px;font-size:11px" onclick="downloadZip('${escapeHtml(z.path)}')"><i class="fas fa-download"></i></button>
            <button class="btn-action danger" style="padding:6px 12px;font-size:11px" onclick="deleteOwnerZip('${escapeHtml(z.path)}')"><i class="fas fa-trash"></i></button>
          </div>
        </div>`;
    });
  } catch(e){ toast('Failed to load ZIPs', true); }
}

async function downloadAllZips(){ window.open('/api/owner/zips/download-all', '_blank'); }
async function downloadZip(path){ window.open('/api/owner/zips/download?path='+encodeURIComponent(path), '_blank'); }

async function deleteOwnerZip(path){
  if(!confirm('Delete this ZIP?')) return;
  const r = await fetch('/api/owner/zips/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path})});
  const d = await r.json();
  toast(d.success ? 'Deleted' : 'Failed', !d.success);
  if(d.success) loadOwnerZips();
}

async function addAnnouncement(){
  const text = document.getElementById('announce-text').value.trim();
  if(!text){ toast('Enter announcement text', true); return; }
  const r = await fetch('/api/owner/announcements/add', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text})});
  const d = await r.json();
  if(d.success){ document.getElementById('announce-text').value=''; toast('Announcement sent'); loadAnnouncements(); }
  else toast('Failed', true);
}

async function loadAnnouncements(){
  try{
    const r = await fetch('/api/owner/announcements');
    const d = await r.json();
    const list = document.getElementById('announce-list');
    if(!list) return;
    list.innerHTML = '';
    if(!(d.list||[]).length){ list.innerHTML = '<div style="color:#9aa9b3;font-size:13px">No announcements yet.</div>'; return; }
    (d.list||[]).forEach((a,i)=>{
      list.innerHTML += `
        <div class="announce-card">
          <div class="a-text"><i class="fas fa-bullhorn"></i> ${escapeHtml(a.text)}</div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="a-time">${escapeHtml(a.time||'')}</span>
            <button class="btn-action danger" style="padding:4px 10px;font-size:11px" onclick="deleteAnnouncement(${i})">Del</button>
          </div>
        </div>`;
    });
  } catch(e){}
}

async function deleteAnnouncement(idx){
  const r = await fetch('/api/owner/announcements/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({index:idx})});
  const d = await r.json();
  if(d.success){ toast('Deleted'); loadAnnouncements(); } else toast('Failed', true);
}

async function savePanelSettings(){
  const name = document.getElementById('panel-name-inp').value.trim();
  const welcome = document.getElementById('panel-welcome-inp').value.trim();
  const r = await fetch('/api/owner/config/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({panel_name:name, welcome_msg:welcome})});
  const d = await r.json();
  toast(d.success ? 'Settings saved' : 'Failed', !d.success);
}

async function broadcastMsg(){
  const msg = document.getElementById('broadcast-msg').value.trim();
  if(!msg){ toast('Enter message', true); return; }
  const r = await fetch('/api/owner/broadcast', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:msg})});
  const d = await r.json();
  toast(d.success ? '<i class="fas fa-satellite-dish"></i> Broadcast sent to ' + (d.count||0) + ' users' : 'Failed', !d.success);
}

async function ownerAction(action){
  const labels = {clear_all_logs:'Clear all logs?', kick_all_users:'Kick ALL users?', reset_stats:'Reset stats?', restart_panel:'Restart panel now?'};
  if(!confirm(labels[action]||action+'?')) return;
  const r = await fetch('/api/owner/action', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action})});
  const d = await r.json();
  toast(d.success ? 'Done: '+action : 'Failed', !d.success);
  if(d.success && action==='kick_all_users') loadOwnerPanel();
}

/* ─── Bot Lock ─────────────────────────────────────────── */
async function toggleBotLock(){
  const chk = document.getElementById('bot-lock-chk');
  const r = await fetch('/api/owner/bot-lock', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({locked: chk.checked})});
  const d = await r.json();
  toast(d.success ? (chk.checked ? '🔒 Bot locked — Maintenance mode ON' : '🔓 Bot unlocked — Operating normally') : 'Failed', !d.success);
}
async function saveBotLockMsg(){
  const msg = document.getElementById('bot-lock-msg').value.trim();
  if(!msg){ toast('Enter a message first', true); return; }
  const r = await fetch('/api/owner/bot-lock', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message: msg})});
  const d = await r.json();
  toast(d.success ? '✅ Maintenance message saved' : 'Failed', !d.success);
}

/* ─── Star Payment ─────────────────────────────────────── */
async function saveStarPayment(){
  const price = parseInt(document.getElementById('star-price').value) || 1;
  const label = document.getElementById('star-label').value.trim() || 'دعم بنجمة';
  const r = await fetch('/api/owner/star-payment', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({price, label})});
  const d = await r.json();
  toast(d.success ? '⭐ Star payment settings saved' : 'Failed', !d.success);
}

/* ─── Proof Channel ────────────────────────────────────── */
async function saveProofChannel(){
  const ch = document.getElementById('proof-channel').value.trim();
  const r = await fetch('/api/owner/proof-channel', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({channel: ch})});
  const d = await r.json();
  toast(d.success ? (ch ? '📡 Proof channel saved: '+ch : '🗑 Proof channel removed') : 'Failed', !d.success);
}

/* ─── Support Tickets ──────────────────────────────────── */
async function loadSupportTickets(){
  const el = document.getElementById('support-tickets-list');
  if(!el) return;
  try{
    const r = await fetch('/api/owner/support-tickets');
    const d = await r.json();
    const tickets = Object.entries(d.tickets || {}).reverse().slice(0, 30);
    if(!tickets.length){
      el.innerHTML = '<div style="color:#9aa9b3;font-size:13px;padding:10px 0">No support tickets yet.</div>';
      return;
    }
    el.innerHTML = tickets.map(([tid, t])=>{
      const isOpen = t.status === 'open';
      const icon = isOpen ? '🔴' : '✅';
      const bg = isOpen ? 'rgba(229,57,53,.08)' : 'rgba(46,204,113,.06)';
      const border = isOpen ? '#e5393533' : '#2ecc7133';
      return `<div style="background:${bg};border:1px solid ${border};border-radius:8px;padding:12px;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <span style="font-weight:600;color:#c8d4dc">${icon} ${escapeHtml(t.user_name||'')} <span style="color:#7a8c98;font-size:11px">(${t.user_id||''})</span></span>
          <span style="font-size:11px;color:#7a8c98">${(t.timestamp||'').slice(0,16)}</span>
        </div>
        <div style="font-size:13px;color:#9aa9b3;margin-bottom:8px">${escapeHtml(t.message||'')}</div>
        ${t.reply ? `<div style="font-size:12px;color:#2ecc71;margin-bottom:8px">↩️ Reply: ${escapeHtml(t.reply)}</div>` : ''}
      </div>`;
    }).join('');
  }catch(e){ el.innerHTML = '<div style="color:#e53935">Failed to load tickets</div>'; }
}

/* --- New owner functions --- */
async function ownerSetBan(username, banned){
  const label = banned ? 'Ban user '+username+'?' : 'Unban user '+username+'?';
  if(!confirm(label)) return;
  const r = await fetch('/api/users/update', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username, banned})});
  const d = await r.json();
  toast(d.success ? (banned ? username+' banned' : username+' unbanned') : 'Failed', !d.success);
  if(d.success) loadOwnerPanel();
}

async function ownerKickUser(username){
  if(!confirm('Kick user '+username+' (log them out)?')) return;
  const r = await fetch('/api/owner/kick-user', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username})});
  const d = await r.json();
  toast(d.success ? username+' kicked' : 'Failed', !d.success);
  if(d.success) loadOwnerPanel();
}

async function ownerResetPass(username){
  const newPass = prompt('New password for '+username+':');
  if(!newPass || newPass.length < 4){ if(newPass!==null) toast('Password too short (min 4 chars)', true); return; }
  const r = await fetch('/api/users/update', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username, password:newPass})});
  const d = await r.json();
  toast(d.success ? 'Password reset for '+username : 'Failed', !d.success);
}

async function ownerAddUser(){
  const u = document.getElementById('ow-new-uname').value.trim();
  const p = document.getElementById('ow-new-pass').value;
  const ms = parseInt(document.getElementById('ow-new-msess').value)||999;
  const msrv = parseInt(document.getElementById('ow-new-msrv').value)||1;
  const mf = document.getElementById('ow-new-mfile').value.trim()||'main.py';
  if(!u||!p){ toast('Username and password are required', true); return; }
  const r = await fetch('/api/users/add', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:u,password:p,max_sessions:ms,max_servers:msrv,main_file:mf})});
  const d = await r.json();
  if(d.success){
    toast('User '+u+' added');
    document.getElementById('ow-new-uname').value='';
    document.getElementById('ow-new-pass').value='';
    loadOwnerPanel();
  } else toast('Failed: '+(d.error||''), true);
}

async function ownerChangeUsername(){
  const newU = document.getElementById('mc-new-uname').value.trim();
  if(!newU){ toast('Enter new username', true); return; }
  if(!confirm('Change master username to "'+newU+'"? You will need to log in with the new username.')) return;
  const r = await fetch('/api/master/change-username', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({new_username:newU})});
  const d = await r.json();
  toast(d.success ? 'Username changed! Please log in again.' : 'Failed', !d.success);
  if(d.success) setTimeout(()=>location.href='/logout', 1500);
}

async function ownerChangePassword(){
  const cur = document.getElementById('mc-cur-pass').value;
  const nw = document.getElementById('mc-new-pass').value;
  if(!cur||!nw){ toast('Fill both fields', true); return; }
  if(nw.length < 4){ toast('Password too short (min 4 chars)', true); return; }
  const r = await fetch('/api/master/change-password', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({current_password:cur, new_password:nw})});
  const d = await r.json();
  toast(d.success ? 'Password changed!' : 'Wrong current password', !d.success);
  if(d.success){ document.getElementById('mc-cur-pass').value=''; document.getElementById('mc-new-pass').value=''; }
}

async function ownerChangePort(){
  const p = parseInt(document.getElementById('mc-port').value);
  if(!p||p<1024||p>65535){ toast('Invalid port (1024-65535)', true); return; }
  if(!confirm('Change port to '+p+' and restart panel?')) return;
  await fetch('/api/master/change-port', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({port:p})});
  toast('Restarting panel on port '+p+'...');
}

async function loadOwnerActivityFeed(){
  try{
    const r = await fetch('/api/activity');
    const d = await r.json();
    const el = document.getElementById('ow-activity-feed');
    if(!el) return;
    const events = (d.events||[]).slice(0,15);
    if(!events.length){ el.innerHTML='<div style="color:#9aa9b3;font-size:13px">No activity yet.</div>'; return; }
    el.innerHTML = events.map(e=>{
      const cat = (e.action||'').startsWith('auth') ? 'auth' : (e.action||'').startsWith('owner') ? 'owner' : (e.action||'').startsWith('server.user') ? 'user' : 'other';
      const icons = {auth:'<i class="fas fa-sign-in-alt"></i>',owner:'<i class="fas fa-crown"></i>',user:'<i class="fas fa-user"></i>',other:'<i class="fas fa-bolt"></i>'};
      return `<div class="feed-item">
        <div class="feed-icon ${cat}">${icons[cat]||icons.other}</div>
        <div class="feed-body">
          <div class="feed-action"><span style="color:#29c7d3">${escapeHtml(e.username||'-')}</span> — ${escapeHtml(e.action||'')}</div>
          ${e.details?`<div class="feed-detail">${escapeHtml(e.details)}</div>`:''}
          <div class="feed-time">${escapeHtml(e.ip||'')} ${e.ip&&e.time_text?'|':''} ${escapeHtml(e.time_text||'')}</div>
        </div>
      </div>`;
    }).join('');
  } catch(e){}
}

/* =========== PORT COPY =========== */
function copyPort(){
  const portEl = document.getElementById('port-display');
  const port = portEl.textContent;
  navigator.clipboard.writeText(port).then(()=>{
    toast('Port '+port+' copied!');
  }).catch(()=>{
    alert('Port: '+port);
  });
}
</script>
</body>
</html>
'''

# =============================================================================
# 13)  مسارات الـ Flask
# =============================================================================
@app.route('/')
@login_required
def index():
    return get_server_list_html(session['username'])

@app.route('/server/<server_id>')
@login_required
def server_detail(server_id):
    username = session['username']
    catalog = get_server_catalog(username)
    if not catalog:
        return redirect('/')
    if not catalog:
        return redirect('/')
    server = next((item for item in catalog if item.get('id') == server_id), catalog[0])
    is_master = (username == MASTER_USERNAME)
    return render_template_string(
        get_html_template(is_master, username=username, server=server),
        session=session,
        user_path=get_user_path(username),
        server=server
    )

@app.route('/api/login/telegram', methods=['POST'])
def telegram_login():
    """
    تسجيل الدخول عبر بيانات البوت
    يتطلب: username, password, telegram_id (اختياري للتحقق)
    """
    try:
        data = request.json or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        telegram_id = data.get('telegram_id')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Missing credentials'}), 400
        
        h = hashlib.sha256(password.encode()).hexdigest()
        users = load_users()
        
        if username not in users:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        user_data = users[username]
        if not isinstance(user_data, dict):
            return jsonify({'success': False, 'error': 'Invalid user data'}), 400
        
        if user_data.get('password') != h:
            return jsonify({'success': False, 'error': 'Invalid password'}), 401
        
        if telegram_id and user_data.get('telegram_id') != telegram_id:
            return jsonify({'success': False, 'error': 'Telegram ID mismatch'}), 403
        
        if not can_user_login(username):
            return jsonify({'success': False, 'error': 'User login not allowed'}), 403
        
        session.permanent = True
        session['logged_in'] = True
        session['username'] = username
        register_session(username)
        os.makedirs(get_user_path(username), exist_ok=True)
        log_activity(username, 'auth.login.telegram', 'Telegram login successful')
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'username': username,
            'redirect': '/'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        return render_template_string(LOGIN_TEMPLATE, error=None)
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    h = hashlib.sha256(password.encode()).hexdigest()
    
    # التحقق من الأدمن الرئيسي
    if username == MASTER_USERNAME and h == MASTER_PASSWORD_HASH:
        session.permanent = True
        session['logged_in'] = True
        session['username'] = username
        register_session(username)
        log_activity(username, 'auth.login', 'Master login successful')
        return redirect('/')
    
    # التحقق من المستخدمين (سواء تم إنشاؤهم من الموقع أو البوت)
    users = load_users()
    if username in users:
        user_data = users[username]
        # التحقق من الحظر
        if user_data.get('banned', False):
            return render_template_string(LOGIN_TEMPLATE, error='❌ هذا الحساب محظور')
            
        if user_data.get('password') == h:
            # إعادة ضبط العداد القديم (جلسات يتيمة بعد إغلاق المتصفح)
            sessions = load_user_sessions()
            sessions[username] = 0
            save_user_sessions(sessions)
            session.permanent = True
            session['logged_in'] = True
            session['username'] = username
            register_session(username)
            os.makedirs(get_user_path(username), exist_ok=True)
            log_activity(username, 'auth.login', 'User login successful')
            return redirect('/')
            
    log_activity(username or '-', 'auth.login.failed', 'Invalid credentials')
    return render_template_string(LOGIN_TEMPLATE, error='❌ بيانات الدخول غير صحيحة')

@app.route('/logout')
def logout():
    if 'username' in session:
        log_activity(session['username'], 'auth.logout', 'User logged out')
        unregister_session(session['username'])
    session.clear()
    return redirect('/login')

@app.route('/download/panel_full.zip')
@master_required
def download_panel_zip():
    zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'panel_full.zip')
    zip_path = os.path.abspath(zip_path)
    if not os.path.exists(zip_path):
        return "File not found", 404
    return send_file(zip_path, as_attachment=True, download_name='panel_full.zip')

@app.route('/access/<token>')
def server_access(token):
    """
    دخول مباشر لسيرفر محدد عبر توكن فريد — كل سيرفر له رابطه الخاص المعزول.
    المستخدم يصل فقط لحسابه المرتبط بهذا التوكن ولا يستطيع الوصول لأي حساب آخر.
    """
    if not token or len(token) < 16:
        return redirect('/login')
    users = load_users()
    matched_user = None
    for uname, udata in users.items():
        if isinstance(udata, dict) and udata.get('access_token') == token:
            matched_user = uname
            break
    if not matched_user:
        log_activity('-', 'auth.token.invalid', f'Invalid access token: {token[:8]}...')
        return render_template_string(LOGIN_TEMPLATE, error='❌ رابط الدخول غير صالح أو منتهي الصلاحية')
    udata = users[matched_user]
    if udata.get('banned', False):
        return render_template_string(LOGIN_TEMPLATE, error='❌ هذا الحساب محظور')
    if not can_user_login(matched_user):
        return render_template_string(LOGIN_TEMPLATE, error='❌ تسجيل الدخول غير مسموح به لهذا الحساب')
    session.permanent = True
    session['logged_in'] = True
    session['username'] = matched_user
    register_session(matched_user)
    os.makedirs(get_user_path(matched_user), exist_ok=True)
    log_activity(matched_user, 'auth.token.login', f'Token-based login from /access/ route')
    return redirect('/')

@app.route('/api/files/main-file')
@login_required
def get_main_file_api():
    """جلب الملف الأساسي للمستخدم الحالي"""
    username = session['username']
    if username == MASTER_USERNAME:
        main_file = MASTER_CONFIG.get('main_file', 'main.py')
    else:
        users = load_users()
        main_file = users.get(username, {}).get('main_file', 'main.py') if isinstance(users.get(username), dict) else 'main.py'
    return jsonify({'success': True, 'main_file': main_file})

@app.route('/api/profile')
@login_required
def get_profile():
    u = session['username']
    p = get_user_path(u)
    size = 0
    if os.path.exists(p):
        for r, d, f in os.walk(p):
            for fl in f:
                fp = os.path.join(r, fl)
                if os.path.exists(fp):
                    size += os.path.getsize(fp)
    users = load_users()
    ud = users.get(u, {})
    return jsonify({
        'username': u,
        'is_master': u == MASTER_USERNAME,
        'created': ud.get('created', datetime.now().isoformat()) if isinstance(ud, dict) else datetime.now().isoformat(),
        'expiry': ud.get('expiry', '∞') if isinstance(ud, dict) else '∞',
        'disk_usage_gb': size / (1024**3)
    })

@app.route('/api/system')
@login_required
def system_info():
    return jsonify(get_system_stats())

@app.route('/api/sysinfo')
@login_required
def sysinfo():
    return jsonify({'info': f"Platform: {platform.platform()}\nCPU: {psutil.cpu_percent()}%\nMemory: {psutil.virtual_memory().percent}%"})

@app.route('/api/stats')
@login_required
def api_stats():
    """مسار /api/stats — يعرض إحصائيات النظام بصيغة JSON"""
    try:
        s = get_system_stats()
        return jsonify({
            'success': True,
            'cpu': {
                'percent': round(s.get('cpu_percent', 0), 2),
                'label': f"{round(s.get('cpu_percent', 0), 2)}%"
            },
            'memory': {
                'percent': round(s.get('memory_percent', 0), 2),
                'used_mb': round(s.get('memory_used_mb', 0), 1),
                'total_mb': round(s.get('memory_total_mb', 0), 1),
                'used_gb': round(s.get('memory_used_gb', 0), 2),
                'total_gb': round(s.get('memory_total_gb', 0), 2),
                'label': f"{round(s.get('memory_used_mb', 0), 1)} MiB / {round(s.get('memory_total_mb', 0), 0)} MiB"
            },
            'disk': {
                'percent': round(s.get('disk_percent', 0), 2),
                'used_gb': round(s.get('disk_used_gb', 0), 2),
                'total_gb': round(s.get('disk_total_gb', 0), 2),
                'label': f"{round(s.get('disk_used_gb', 0), 2)} GiB / {round(s.get('disk_total_gb', 0), 0)} GiB"
            },
            'network': {
                'in_kb': round(s.get('net_in_kb', 0), 2),
                'out_kb': round(s.get('net_out_kb', 0), 2)
            },
            'uptime': s.get('uptime', 0),
            'hostname': s.get('hostname', '-'),
            'public_ip': s.get('public_ip', 'N/A'),
            'platform': s.get('platform', '-'),
            'port': 20048
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/system/action', methods=['POST'])
@login_required
def system_action_api():
    a = (request.json or {}).get('action')
    try:
        if a == 'clean':
            gc.collect()
        elif a == 'update':
            subprocess.run(['apt-get', 'update'], capture_output=True, timeout=120)
        log_activity(session['username'], 'system.action', a or '')
        return jsonify({'success': True, 'action': a})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ----- Activity feed -----
@app.route('/api/activity')
@login_required
def activity_api():
    data = load_json_file(ACTIVITY_FILE, {'events': []})
    events = data.get('events', [])
    if session.get('username') != MASTER_USERNAME:
        events = [e for e in events if e.get('username') == session.get('username')]
    return jsonify({'events': events[:200]})

# ----- ملفات -----
@app.route('/api/files')
@login_required
def list_files_api():
    p = request.args.get('path', get_user_path(session['username']))
    if not is_path_allowed(session['username'], p):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    files = []
    try:
        for n in sorted(os.listdir(p), key=lambda x: (not os.path.isdir(os.path.join(p, x)), x.lower())):
            fp = os.path.join(p, n)
            files.append({
                'name': n,
                'is_dir': os.path.isdir(fp),
                'size': f"{os.path.getsize(fp)//1024} KB" if os.path.isfile(fp) else '',
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'files': files})

@app.route('/api/files/download')
@login_required
def download_file_api():
    p = request.args.get('path', '')
    username = session['username']
    if not p or not is_path_allowed(username, p) or not os.path.isfile(p):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    return send_file(p, as_attachment=True, download_name=os.path.basename(p))

@app.route('/api/files/upload', methods=['POST'])
@login_required
def upload_file_api():
    f = request.files.get('file')
    p = request.form.get('path', get_user_path(session['username']))
    if not f or not is_path_allowed(session['username'], p):
        return jsonify({'success': False, 'error': 'غير مسموح'}), 400

    # 🔒 تنظيف اسم الملف ومنع path traversal
    safe_name = secure_filename_safe(f.filename)

    # 🔒 منع الامتدادات الثنائية الخطيرة فقط
    if is_extension_blocked(safe_name) and session['username'] != MASTER_USERNAME:
        return jsonify({'success': False, 'error': f'❌ امتداد الملف محظور: {os.path.splitext(safe_name)[1]}'}), 403

    # 🔒 حد أقصى لحجم الملف 100MB للمستخدمين العاديين
    if session['username'] != MASTER_USERNAME:
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > 100 * 1024 * 1024:
            return jsonify({'success': False, 'error': '❌ حجم الملف يتجاوز 100MB'}), 413

    filepath = os.path.join(p, safe_name)
    if os.path.islink(filepath) or not is_path_allowed(session['username'], filepath):
        return jsonify({'success': False, 'error': 'مسار الملف غير آمن'}), 403
    f.save(filepath)
    log_activity(session['username'], 'server.file.upload', f.filename)
    
    # إذا كان الملف المرفوع هو main.py، قم بتشغيله تلقائياً
    if f.filename.lower() == 'main.py':
        # تعيينه كملف رئيسي
        users = load_users()
        username = session['username']
        if username == MASTER_USERNAME:
            MASTER_CONFIG['main_file'] = f.filename
            save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
        elif username in users:
            users[username]['main_file'] = f.filename
            save_users(users)
        
        # تشغيل الملف في ثريد منفصل لتجنب تأخير الاستجابة
        def auto_run():
            time.sleep(1) # انتظار بسيط للتأكد من حفظ الملف
            try:
                requests.post(f'http://127.0.0.1:{MASTER_CONFIG.get("port", 3177)}/api/file/run', 
                             json={'filename': f.filename, 'path': p},
                             cookies=request.cookies)
            except: pass
        
        threading.Thread(target=auto_run, daemon=True).start()
        return jsonify({'success': True, 'auto_run': True})

    return jsonify({'success': True})

@app.route('/api/files/folder', methods=['POST'])
@login_required
def create_folder_api():
    d = request.json
    if not is_path_allowed(session['username'], d['path']):
        return jsonify({'success': False}), 403
    os.makedirs(d['path'], exist_ok=True)
    log_activity(session['username'], 'server.file.mkdir', d['path'])
    return jsonify({'success': True})

@app.route('/api/files/create', methods=['POST'])
@login_required
def create_file_api():
    d = request.json
    if not is_path_allowed(session['username'], d['path']):
        return jsonify({'success': False}), 403
    with open(d['path'], 'w', encoding='utf-8') as f:
        f.write(d.get('content', ''))
    log_activity(session['username'], 'server.file.create', d['path'])
    return jsonify({'success': True})

@app.route('/api/files/rename', methods=['POST'])
@login_required
def rename_file_api():
    d = request.json or {}
    old_path = d.get('old_path', '')
    new_name = d.get('new_name', '').strip()
    username = session['username']
    # منع اسم فارغ أو يحتوي على مسارات
    if not new_name or '/' in new_name or '..' in new_name or new_name.startswith('.'):
        return jsonify({'success': False, 'error': 'اسم غير صالح'}), 400
    if not is_path_allowed(username, old_path):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    parent = os.path.dirname(old_path)
    new_path = os.path.join(parent, new_name)
    # تأكد أن المسار الجديد أيضاً داخل مجلد المستخدم
    if not is_path_allowed(username, new_path):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    if os.path.exists(new_path):
        return jsonify({'success': False, 'error': 'الاسم مستخدم بالفعل'}), 409
    try:
        os.rename(old_path, new_path)
        log_activity(username, 'server.file.rename', f'{old_path} -> {new_name}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/move', methods=['POST'])
@login_required
def move_file_api():
    d = request.json or {}
    username = session['username']
    old_path = d.get('old_path', '')
    dest_dir = d.get('dest_dir', '')
    if not old_path or not dest_dir or not is_path_allowed(username, old_path) or not is_path_allowed(username, dest_dir):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    if not os.path.exists(old_path) or not os.path.isdir(dest_dir):
        return jsonify({'success': False, 'error': 'Source or destination not found'}), 404
    new_path = os.path.join(dest_dir, os.path.basename(old_path))
    if not is_path_allowed(username, new_path) or os.path.exists(new_path):
        return jsonify({'success': False, 'error': 'Destination already contains this name'}), 409
    try:
        shutil.move(old_path, new_path)
        log_activity(username, 'server.file.move', f'{old_path} -> {new_path}')
        return jsonify({'success': True, 'path': new_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/archive', methods=['POST'])
@login_required
def archive_files_api():
    d = request.json or {}
    username = session['username']
    base = d.get('path', '')
    names = d.get('names') or []
    archive_name = secure_filename_safe(d.get('archive_name', 'archive.zip'))
    if not archive_name.lower().endswith('.zip'):
        archive_name += '.zip'
    if not base or not names or not is_path_allowed(username, base):
        return jsonify({'success': False, 'error': 'Invalid selection'}), 400
    archive_path = os.path.join(base, archive_name)
    if not is_path_allowed(username, archive_path):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    try:
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name in names:
                if not isinstance(name, str) or not name or '/' in name or '\\' in name or name in ('.', '..'):
                    continue
                source = os.path.join(base, name)
                if not os.path.exists(source) or not is_path_allowed(username, source) or os.path.realpath(source) == os.path.realpath(archive_path):
                    continue
                if os.path.isdir(source):
                    for root, dirs, files in os.walk(source):
                        for fn in files:
                            full = os.path.join(root, fn)
                            zf.write(full, os.path.relpath(full, base))
                else:
                    zf.write(source, name)
        log_activity(username, 'server.file.archive', archive_path)
        return jsonify({'success': True, 'archive': archive_name})
    except Exception as e:
        try:
            if os.path.exists(archive_path): os.remove(archive_path)
        except Exception: pass
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/files/delete', methods=['POST'])
@login_required
def delete_file_api():
    d = request.json
    p = d['path']
    if not is_path_allowed(session['username'], p):
        return jsonify({'success': False}), 403
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
    elif os.path.isfile(p):
        os.remove(p)
    log_activity(session['username'], 'server.file.delete', p)
    return jsonify({'success': True})

@app.route('/api/files/delete-many', methods=['POST'])
@login_required
def delete_many_files_api():
    d = request.json or {}
    username = session['username']
    base = d.get('path', '')
    names = d.get('names') or []
    if not base or not is_path_allowed(username, base) or not isinstance(names, list):
        return jsonify({'success': False, 'error': 'Invalid selection'}), 400
    deleted = 0
    for name in names:
        if not isinstance(name, str) or not name or '/' in name or '\\' in name or name in ('.', '..'):
            continue
        target = os.path.join(base, name)
        if not is_path_allowed(username, target) or not os.path.lexists(target):
            continue
        try:
            if os.path.isdir(target) and not os.path.islink(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
            log_activity(username, 'server.file.delete', target)
            deleted += 1
        except Exception:
            continue
    return jsonify({'success': True, 'deleted': deleted})

@app.route('/api/files/content')
@login_required
def get_file_content():
    p = request.args.get('path')
    if not p or not is_path_allowed(session['username'], p):
        return jsonify({'success': False}), 403
    try:
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            log_activity(session['username'], 'server.file.read', p)
            return jsonify({'content': f.read()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/files/save', methods=['POST'])
@login_required
def save_file_api():
    d = request.json
    if not is_path_allowed(session['username'], d['path']):
        return jsonify({'success': False}), 403
    with open(d['path'], 'w', encoding='utf-8') as f:
        f.write(d.get('content', ''))
    log_activity(session['username'], 'server.file.write', d['path'])
    return jsonify({'success': True})

@app.route('/api/files/set-main', methods=['POST'])
@login_required
def set_main_file_api():
    """تعيين ملف كملف التشغيل الأساسي للمستخدم"""
    d = request.json or {}
    filename = d.get('filename', '')
    path = d.get('path', '')
    username = session['username']
    if not filename:
        return jsonify({'success': False, 'error': 'No filename'})
    users = load_users()
    if username == MASTER_USERNAME:
        MASTER_CONFIG['main_file'] = filename
        save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
    elif username in users:
        users[username]['main_file'] = filename
        save_users(users)
    log_activity(username, 'server.file.set-main', filename)
    return jsonify({'success': True, 'main_file': filename})

# ----- تشغيل/إيقاف الملفات -----
@app.route('/api/file/run', methods=['POST'])
@login_required
def run_file_api():
    import shlex
    d = request.json or {}
    requested_dir = d.get('path', '')
    if not is_path_allowed(session['username'], requested_dir):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    filepath = os.path.join(requested_dir, d.get('filename', ''))
    if not is_path_allowed(session['username'], filepath) or not os.path.isfile(filepath):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    if d.get('filename', '').lower().endswith('.zip'):
        extract_dir = os.path.join(d['path'], d['filename'].replace('.zip', ''))
        os.makedirs(extract_dir, exist_ok=True)
        main = extract_and_find_main(filepath, extract_dir)
        if main:
            filepath = main
        else:
            return jsonify({'success': False, 'error': 'Main file not found'})
    work_dir = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    username = session['username']

    # تثبيت المكتبات يتم داخل حاوية Docker فقط؛ لا نثبت كود المستخدم في بيئة اللوحة.

    # 🔒 عزل كامل: حاوية Docker خاصة بكل ملف (أو sandbox مُقوّى لو Docker غير متاح)
    sandbox_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox_runner.py')
    ext = filepath.split('.')[-1].lower()
    iso_mode = 'plain'
    if isolation is not None:
        run_cmd, iso_mode = isolation.build_run_command(
            username, filepath, sandbox_script,
            is_master=(username == MASTER_USERNAME),
            fallback_cmd=get_run_command(filepath))
    else:
        run_cmd = get_run_command(filepath)
    if not run_cmd:
        return jsonify({'success': False, 'error': 'العزل غير متاح على هذه الاستضافة؛ شغّل Docker daemon منفصلاً قبل تشغيل الملف.'}), 503

    badge = {'docker': '[🐳 CONTAINER]', 'sandbox': '[🔒 SANDBOX]'}.get(iso_mode, '')
    parts = [f'echo "[*] Starting: {filename} {badge}"']
    if iso_mode != 'docker':
        # داخل الحاوية يتم تثبيت المكتبات بالداخل، وخارجها فقط لمجلد الملف نفسه
        parts.insert(0, 'echo "container@pterodactyl~ Server marked as starting..."; echo "[Pterodactyl Daemon]: Checking server disk space usage, this could take a few seconds..."; echo "[Pterodactyl Daemon]: Updating process configuration files..."; echo "[Pterodactyl Daemon]: Ensuring file permissions are set correctly, this could take a few seconds..."; echo "container@pterodactyl~ Server marked as starting..."; echo "[Pterodactyl Daemon]: Pulling Docker container image, this could take a few minutes to complete..."; echo "[Pterodactyl Daemon]: Finished pulling Docker container image"')
        req_path = os.path.join(work_dir, 'requirements.txt')
        if os.path.exists(req_path):
            parts.insert(0, 'echo "[*] Installing dependencies from requirements.txt..."')
            parts.insert(1, f'{sys.executable} -m pip install --break-system-packages -r {shlex.quote(req_path)} 2>&1')
            parts.insert(2, 'echo "[*] Dependencies ready."')
    parts.append(run_cmd)
    full_cmd = ' && '.join(parts)
    try:
        kwargs = dict(shell=True, cwd=work_dir,
                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                      stderr=subprocess.STDOUT, text=True, bufsize=1)
        if isolation is not None:
            kwargs['env'] = isolation.clean_child_env()
        if hasattr(os, 'setsid'):
            kwargs['preexec_fn'] = os.setsid
        p = subprocess.Popen(full_cmd, **kwargs)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    pid = f"{session['username']}_{d.get('filename','f')}_{int(time.time())}"
    file_processes[pid] = {'process': p, 'filename': d.get('filename',''), 'username': session['username'], 'output': [], 'filepath': filepath, 'iso_mode': iso_mode}
    threading.Thread(target=read_process_output, args=(pid, p), kwargs={'store': file_processes}, daemon=True).start()
    log_activity(session['username'], 'server.file.run', f"{d.get('filename','')} ({pid})")
    return jsonify({'success': True, 'process_id': pid})

@app.route('/api/file/stream/<pid>')
@login_required
def stream_file_output(pid):
    def generate():
        last_len = 0
        idle = 0
        while True:
            info = file_processes.get(pid)
            if info is None:
                yield 'data: {"done":true}\n\n'
                return
            output = info.get('output', [])
            if len(output) > last_len:
                for line in output[last_len:]:
                    yield f'data: {json.dumps({"line": line})}\n\n'
                last_len = len(output)
                idle = 0
            process_alive = info['process'].poll() is None
            if not process_alive and len(output) == last_len:
                # العملية انتهت ولا يوجد output جديد
                if idle >= 2:
                    yield 'data: {"done":true}\n\n'
                    return
                idle += 0.15
            elif not process_alive:
                # العملية انتهت لكن لا يزال هناك output للإرسال
                idle = 0
            else:
                # العملية لا تزال شغّالة — لا تُغلق الـ stream أبدًا
                idle = 0
            time.sleep(0.15)
    return app.response_class(generate(), mimetype='text/event-stream',
                               headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/api/file/stop', methods=['POST'])
@login_required
def stop_file_api():
    pid = (request.json or {}).get('process_id')
    if pid in file_processes:
        info = file_processes[pid]
        if info.get('username') != session.get('username') and session.get('username') != MASTER_USERNAME:
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        if isolation is not None and info.get('iso_mode') == 'docker' and info.get('filepath'):
            try:
                isolation.stop_container(info.get('username'), info['filepath'])
            except Exception:
                pass
        try:
            if hasattr(os, 'killpg'):
                os.killpg(os.getpgid(file_processes[pid]['process'].pid), signal.SIGKILL)
            else:
                file_processes[pid]['process'].kill()
        except Exception:
            pass
        log_activity(session['username'], 'server.file.stop', pid)
        del file_processes[pid]
    return jsonify({'success': True})

@app.route('/api/file/output/<pid>')
@login_required
def get_file_output_api(pid):
    if pid in file_processes:
        info = file_processes[pid]
        if info.get('username') != session.get('username') and session.get('username') != MASTER_USERNAME:
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        return jsonify({
            'success': True,
            'output': info.get('output', []),
            'is_running': info['process'].poll() is None
        })
    return jsonify({'success': False})

@app.route('/api/file/input', methods=['POST'])
@login_required
def send_file_input_api():
    d = request.json or {}
    pid = d.get('process_id')
    if pid in file_processes:
        if file_processes[pid].get('username') != session.get('username') and session.get('username') != MASTER_USERNAME:
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        try:
            file_processes[pid]['process'].stdin.write(d.get('input','') + '\n')
            file_processes[pid]['process'].stdin.flush()
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    return jsonify({'success': True})

@app.route('/api/file/running')
@login_required
def get_running_files_api():
    user    = session['username']
    running = []
    dead    = []
    for pid, info in file_processes.items():
        if info['username'] == user or user == MASTER_USERNAME:
            if info['process'].poll() is None:
                running.append({'process_id': pid, 'filename': info['filename'], 'username': info['username']})
            else:
                dead.append(pid)
    for d in dead:
        file_processes.pop(d, None)
    return jsonify({'success': True, 'running': running})

# ----- تنفيذ أوامر -----
@app.route('/api/exec', methods=['POST'])
@login_required
def execute_command_api():
    import re as _re
    def strip_ansi(text):
        return _re.sub(r'\x1b\[[0-9;]*[mGKHFABCDJsurz]|\x1b\[[\?]?[0-9;]*[hlm]|\x1b[()][AB012]|\r', '', text)
    d = request.json
    cmd = d['command']
    username = session['username']

    # 🔒 فحص الأوامر الخطيرة
    blocked, reason = is_command_blocked(cmd, username)
    if blocked:
        log_activity(username, 'security.blocked_cmd', cmd[:120])
        return jsonify({'output': f'🔒 تم حظر الأمر لأسباب أمنية: {reason}', 'success': False})

    # 🔒 تقييد cwd لمجلد المستخدم فقط (عدا المالك)
    user_path = get_user_path(username)
    cwd = d.get('cwd', user_path)
    if username != MASTER_USERNAME:
        try:
            if not os.path.realpath(cwd).startswith(os.path.realpath(user_path)):
                cwd = user_path
        except Exception:
            cwd = user_path
    if not os.path.isdir(cwd):
        cwd = user_path if os.path.isdir(user_path) else BASE_PATH

    log_activity(username, 'server.exec', cmd[:120])
    try:
        # 🔒 بيئة محدودة للمستخدمين العاديين
        safe_env = {
            'HOME': user_path,
            'PATH': '/usr/local/bin:/usr/bin:/bin',
            'TERM': 'dumb',
            'NO_COLOR': '1',
            'TMPDIR': user_path,
        }
        env = os.environ.copy() if username == MASTER_USERNAME else {**safe_env}
        exec_cmd = cmd
        if username != MASTER_USERNAME:
            if isolation is None or isolation.isolation_mode() != 'docker':
                log_activity(username, 'security.blocked_cmd', 'terminal unavailable without Docker')
                return jsonify({'output': 'التيرمنال متاح فقط داخل حاوية Docker معزولة.', 'success': False}), 503
            exec_cmd = isolation.build_shell_command(username, cwd, cmd)
            env = isolation.clean_child_env()
        r = subprocess.run(exec_cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=60, env=env)
        out = strip_ansi(r.stdout + r.stderr)
        if not out.strip():
            out = '(no output)'
        return jsonify({'output': out, 'success': True})
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Timeout (60s)', 'success': False})
    except Exception as e:
        return jsonify({'error': str(e), 'success': False})

# ----- العمليات -----
@app.route('/api/process/start', methods=['POST'])
@login_required
def start_process_api():
    d = request.json
    username = session['username']
    user_path = get_user_path(username)
    cwd = d.get('cwd') or (BASE_PATH if username == MASTER_USERNAME else user_path)
    command = d['command']
    if username != MASTER_USERNAME:
        # 🔒 لا يخرج عن مجلده أبداً
        if not is_path_allowed(username, cwd):
            cwd = user_path
        if isolation is None or isolation.isolation_mode() != 'docker':
            return jsonify({'success': False, 'error': 'العمليات متاحة فقط داخل حاوية Docker معزولة.'}), 503
        command = isolation.build_shell_command(username, cwd, command)
    d = {**d, 'command': command, 'cwd': cwd}
    def run():
        kwargs = dict(shell=True, cwd=cwd)
        if isolation is not None and username != MASTER_USERNAME:
            kwargs['env'] = isolation.clean_child_env()
        if hasattr(os, 'setsid'):
            kwargs['preexec_fn'] = os.setsid
        p = subprocess.Popen(d['command'], **kwargs)
        running_processes[d['name']] = {'process': p, 'owner': session.get('username'), 'command': d['command']}
        p.wait()
    threading.Thread(target=run, daemon=True).start()
    log_activity(session['username'], 'server.process.start', d.get('name',''))
    return jsonify({'success': True})

@app.route('/api/process/stop', methods=['POST'])
@login_required
def stop_process_api():
    n = request.json['name']
    if n in running_processes:
        owner = running_processes[n].get('owner')
        if owner != session.get('username') and session.get('username') != MASTER_USERNAME:
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        try:
            if hasattr(os, 'killpg'):
                os.killpg(os.getpgid(running_processes[n]['process'].pid), signal.SIGKILL)
            else:
                running_processes[n]['process'].kill()
        except Exception:
            pass
        del running_processes[n]
    log_activity(session['username'], 'server.process.stop', n)
    return jsonify({'success': True})

@app.route('/api/process/stop-all', methods=['POST'])
@login_required
def stop_all_processes_api():
    username = session.get('username')
    for name, p in list(running_processes.items()):
        if username != MASTER_USERNAME and p.get('owner') != username:
            continue
        try:
            if hasattr(os, 'killpg'):
                os.killpg(os.getpgid(p['process'].pid), signal.SIGKILL)
            else:
                p['process'].kill()
        except Exception:
            pass
    if username == MASTER_USERNAME:
        running_processes.clear()
    else:
        for name in [n for n, p in running_processes.items() if p.get('owner') == username]:
            running_processes.pop(name, None)
    return jsonify({'success': True})

@app.route('/api/process/list')
@login_required
def list_processes_api():
    procs = {}
    username = session.get('username')
    for n, i in running_processes.items():
        if username != MASTER_USERNAME and i.get('owner') != username:
            continue
        procs[n] = {'status': 'running' if i['process'].poll() is None else 'stopped', 'command': i['command']}
    return jsonify(procs)

# ----- شبكة / بورتات متعددة (Replit-friendly) -----
@app.route('/api/network/scan', methods=['POST'])
@login_required
def scan_ports_api():
    d = request.json
    out = []
    for p in d.get('ports', []):
        try:
            s = socket.socket()
            s.settimeout(1)
            r = s.connect_ex((d['host'], int(p)))
            out.append({'port': p, 'open': r == 0})
            s.close()
        except Exception:
            out.append({'port': p, 'open': False})
    return jsonify({'results': out})

@app.route('/api/ports/list')
@login_required
def list_ports_api():
    return jsonify({'ports': load_ports()})

@app.route('/api/ports/add', methods=['POST'])
@master_required
def add_port_api():
    d = request.json
    try:
        port = int(d.get('port', 0))
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid port'})
    if port <= 0 or port > 65535:
        return jsonify({'success': False, 'error': 'Invalid port range'})
    ports = load_ports()
    if any(p.get('port') == port for p in ports):
        return jsonify({'success': False, 'error': 'Port already exists'})
    ports.append({'port': port, 'note': d.get('note', ''), 'status': 'idle', 'created': datetime.now().isoformat()})
    save_ports(ports)
    log_activity(session['username'], 'server.port.add', str(port))
    return jsonify({'success': True})

@app.route('/api/ports/delete', methods=['POST'])
@master_required
def del_port_api():
    port = (request.json or {}).get('port')
    ports = [p for p in load_ports() if p.get('port') != port]
    save_ports(ports)
    log_activity(session['username'], 'server.port.delete', str(port))
    return jsonify({'success': True})

# ----- مستخدمي اللوحة -----
@app.route('/api/users/list')
@master_required
def list_panel_users_api():
    users = load_users()
    sessions = load_user_sessions()
    return jsonify({'users': [
        {'username': u,
         'max_sessions': users[u].get('max_sessions', 999) if isinstance(users[u], dict) else 999,
         'max_servers': users[u].get('max_servers', 1) if isinstance(users[u], dict) else 1,
         'main_file': users[u].get('main_file', 'main.py') if isinstance(users[u], dict) else 'main.py',
         'server_name': users[u].get('server_name', '') if isinstance(users[u], dict) else '',
         'banned': users[u].get('banned', False) if isinstance(users[u], dict) else False,
         'active_sessions': sessions.get(u, 0)}
        for u in users
    ]})

@app.route('/api/users/add', methods=['POST'])
@master_required
def add_panel_user_api():
    d = request.json
    users = load_users()
    users[d['username']] = {
        'password': hashlib.sha256(d['password'].encode()).hexdigest(),
        'max_sessions': int(d.get('max_sessions', 999)),
        'max_servers': int(d.get('max_servers', 1)),
        'main_file': d.get('main_file', 'main.py'),
        'server_name': d.get('server_name', '').strip(),
        'created': datetime.now().isoformat(),
        'expiry': d.get('expiry')
    }
    save_users(users)
    os.makedirs(os.path.join(USERS_FOLDER, d['username']), exist_ok=True)
    log_activity(session['username'], 'server.user.add', d['username'])
    return jsonify({'success': True})

@app.route('/api/users/update', methods=['POST'])
@master_required
def update_panel_user_api():
    d = request.json
    users = load_users()
    uname = d.get('username')
    if uname not in users:
        return jsonify({'success': False, 'error': 'User not found'})
    if d.get('password'):
        users[uname]['password'] = hashlib.sha256(d['password'].encode()).hexdigest()
    if d.get('max_servers') is not None:
        users[uname]['max_servers'] = int(d['max_servers'])
    if d.get('main_file') is not None:
        users[uname]['main_file'] = d['main_file']
    if d.get('server_name') is not None:
        users[uname]['server_name'] = str(d['server_name']).strip()
    if d.get('max_sessions') is not None:
        users[uname]['max_sessions'] = int(d['max_sessions'])
    if 'banned' in d:
        users[uname]['banned'] = bool(d['banned'])
    save_users(users)
    log_activity(session['username'], 'server.user.update', uname + (' BANNED' if d.get('banned') else (' UNBANNED' if 'banned' in d else '')))
    return jsonify({'success': True})

@app.route('/api/user/settings', methods=['GET', 'POST'])
@login_required
def user_settings_api():
    username = session['username']
    if username == MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Use master settings'}), 403
    users = load_users()
    if username not in users or not isinstance(users[username], dict):
        return jsonify({'success': False, 'error': 'User not found'}), 404
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'runtime': users[username].get('runtime', 'python'),
            'version': users[username].get('runtime_version', '3.11'),
            'main_file': users[username].get('main_file', 'main.py')
        })
    d = request.json or {}
    runtime = d.get('runtime', 'python')
    version = d.get('version', '3.11')
    main_file = (d.get('main_file') or '').strip()
    valid_runtimes = {'python': ['3.9','3.10','3.11','3.12'], 'nodejs': ['16','18','20','22']}
    if runtime not in valid_runtimes or version not in valid_runtimes.get(runtime, []):
        return jsonify({'success': False, 'error': 'Invalid runtime or version'}), 400
    if not main_file or '/' in main_file or '..' in main_file:
        return jsonify({'success': False, 'error': 'Invalid main file name'}), 400
    users[username]['runtime'] = runtime
    users[username]['runtime_version'] = version
    users[username]['main_file'] = main_file
    save_users(users)
    log_activity(username, 'user.settings.update', f'{runtime} {version} / {main_file}')
    return jsonify({'success': True})

@app.route('/api/user/change-password', methods=['POST'])
@login_required
def user_change_password_api():
    username = session['username']
    if username == MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Use master settings'}), 403
    d = request.json or {}
    cur = d.get('current_password', '')
    nw  = d.get('new_password', '')
    if not cur or not nw:
        return jsonify({'success': False, 'error': 'Missing fields'}), 400
    if len(nw) < 6:
        return jsonify({'success': False, 'error': 'Password too short (min 6 chars)'}), 400
    users = load_users()
    if username not in users or not isinstance(users[username], dict):
        return jsonify({'success': False, 'error': 'User not found'}), 404
    cur_hash = hashlib.sha256(cur.encode()).hexdigest()
    if users[username].get('password') != cur_hash:
        return jsonify({'success': False, 'error': 'Wrong current password'}), 401
    new_hash = hashlib.sha256(nw.encode()).hexdigest()
    users[username]['password'] = new_hash
    users[username]['password_plain'] = nw
    save_users(users)
    log_activity(username, 'user.password.change', 'Password changed by user')
    return jsonify({'success': True})

@app.route('/api/user/delete-account', methods=['POST'])
@login_required
def user_delete_account_api():
    username = session['username']
    if username == MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Cannot delete master account'}), 403
    d = request.json or {}
    password = d.get('password', '')
    if not password:
        return jsonify({'success': False, 'error': 'Password required'}), 400
    users = load_users()
    if username not in users or not isinstance(users[username], dict):
        return jsonify({'success': False, 'error': 'User not found'}), 404
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    if users[username].get('password') != pw_hash:
        return jsonify({'success': False, 'error': 'Wrong password'}), 401
    # إيقاف أي عمليات جارية للمستخدم
    user_path = get_user_path(username)
    for pid in list(file_processes.keys()):
        info = file_processes.get(pid, {})
        if info.get('username') == username or str(info.get('path','')).startswith(user_path):
            try:
                if hasattr(os, 'killpg'):
                    os.killpg(os.getpgid(info['process'].pid), signal.SIGKILL)
                else:
                    info['process'].kill()
            except Exception:
                pass
            file_processes.pop(pid, None)
    # حذف مجلد ملفات المستخدم
    import shutil
    try:
        if os.path.exists(user_path) and user_path != BASE_PATH:
            shutil.rmtree(user_path, ignore_errors=True)
    except Exception:
        pass
    # حذف المستخدم من قاعدة البيانات
    del users[username]
    save_users(users)
    unregister_session(username)
    log_activity(username, 'user.account.delete', 'User deleted own account')
    session.clear()
    return jsonify({'success': True})

@app.route('/api/users/delete', methods=['POST'])
@master_required
def delete_panel_user_api():
    d = request.json
    username = d.get('username')
    users = load_users()
    if username in users:
        # 1) إيقاف كافة العمليات الجارية للمستخدم
        for pid in list(file_processes.keys()):
            if file_processes[pid].get('username') == username:
                try:
                    if hasattr(os, 'killpg'):
                        os.killpg(os.getpgid(file_processes[pid]['process'].pid), signal.SIGKILL)
                    else:
                        file_processes[pid]['process'].kill()
                except Exception: pass
                file_processes.pop(pid, None)
        # 2) حذف مجلد البيانات
        user_dir = os.path.join(USERS_FOLDER, username)
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir, ignore_errors=True)
        # 3) حذف الجلسات النشطة
        sessions = load_user_sessions()
        sessions.pop(username, None)
        save_user_sessions(sessions)
        # 4) حذف المستخدم من القائمة
        del users[username]
        save_users(users)
        log_activity(session['username'], 'server.user.delete', username)
    return jsonify({'success': True})

# ----- الملفات الثابتة -----
@app.route('/static/<path:filename>')
def serve_static(filename):
    # static لا يملك صلاحية تصفح panel_data؛ اسم ملف واحد وامتداد واجهة فقط.
    if (filename.startswith('.') or '/' in filename or '..' in filename.split('/')
            or os.path.splitext(filename.lower())[1] not in _PUBLIC_WEB_EXTENSIONS):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return send_from_directory(BASE_PATH, filename)

# ----- استضافة المواقع والـ API -----
_PUBLIC_WEB_EXTENSIONS = {'.html', '.css', '.js', '.mjs', '.map', '.png', '.jpg',
                          '.jpeg', '.gif', '.svg', '.webp', '.ico', '.woff', '.woff2',
                          '.ttf', '.wasm'}

def _public_user_file(username, filename, api=False):
    if not username or username == MASTER_USERNAME or username not in load_users():
        return None
    if not filename or filename.startswith('.') or any(part in ('', '.', '..') for part in filename.split('/')):
        return None
    ext = os.path.splitext(filename.lower())[1]
    if api and ext != '.json':
        return None
    if not api and ext not in _PUBLIC_WEB_EXTENSIONS:
        return None
    user_path = get_user_path(username)
    candidate = os.path.realpath(os.path.join(user_path, filename))
    if not is_path_allowed(username, candidate) or not os.path.isfile(candidate):
        return None
    return user_path

@app.route('/web/<username>/')
@app.route('/web/<username>/<path:filename>')
def serve_user_web(username, filename='index.html'):
    directory = _public_user_file(username, filename, api=False)
    if directory is None:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return send_from_directory(directory, filename)

@app.route('/api-service/<username>/')
@app.route('/api-service/<username>/<path:filename>')
def serve_user_api_files(username, filename='api.json'):
    directory = _public_user_file(username, filename, api=True)
    if directory is None:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return send_from_directory(directory, filename)

# ----- الجدولة -----
@app.route('/api/schedules/list')
@login_required
def list_schedules_api():
    return jsonify({'schedules': list(load_schedules().values())})

@app.route('/api/schedules/add', methods=['POST'])
@login_required
def add_schedule_api():
    d = request.json
    sch = load_schedules()
    sid = str(uuid.uuid4())[:8]
    sch[sid] = {'id': sid, 'name': d['name'], 'command': d['command'], 'schedule': d.get('schedule', '* * * * *'), 'owner': session['username']}
    save_schedules(sch)
    log_activity(session['username'], 'server.schedule.add', d['name'])
    return jsonify({'success': True})

# ----- النسخ -----
@app.route('/api/backups/list')
@master_required
def list_backups_api():
    backs = []
    if os.path.exists(BACKUPS_FOLDER):
        for f in os.listdir(BACKUPS_FOLDER):
            if f.endswith('.tar.gz'):
                backs.append({'name': f, 'size': f"{os.path.getsize(os.path.join(BACKUPS_FOLDER, f))/1024**2:.2f} MB"})
    return jsonify({'backups': backs})

@app.route('/api/backups/create', methods=['POST'])
@master_required
def create_backup_api():
    name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
    try:
        with tarfile.open(os.path.join(BACKUPS_FOLDER, name), 'w:gz') as tar:
            tar.add(BASE_PATH, arcname='backup')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    log_activity(session['username'], 'server.backup.create', name)
    return jsonify({'success': True})

# ----- الحزم -----
@app.route('/api/packages/list')
@master_required
def list_packages_api():
    return jsonify(load_packages())

@app.route('/api/packages/install/pip', methods=['POST'])
@master_required
def install_pip_api():
    pkg = request.json['package']
    subprocess.run([sys.executable, '-m', 'pip', 'install', pkg], capture_output=True)
    pkgs = load_packages()
    if pkg not in pkgs.get('pip', []):
        pkgs.setdefault('pip', []).append(pkg)
        save_packages(pkgs)
    log_activity(session['username'], 'server.package.install', pkg)
    return jsonify({'success': True})

# ----- Docker -----
@app.route('/api/docker/list')
@master_required
def list_docker_api():
    out = []
    try:
        r = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}|{{.Status}}'],
                           capture_output=True, text=True)
        for line in (r.stdout or '').strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 2:
                    out.append({'name': parts[0], 'status': parts[1]})
    except Exception:
        pass
    return jsonify({'containers': out})

@app.route('/api/docker/run', methods=['POST'])
@master_required
def run_docker_api():
    d = request.json
    cmd = ['docker', 'run', '-d']
    if d.get('name'): cmd.extend(['--name', d['name']])
    if d.get('ports'):
        for p in d['ports'].split(','):
            cmd.extend(['-p', p.strip()])
    cmd.append(d['image'])
    subprocess.run(cmd, capture_output=True)
    return jsonify({'success': True})

# ----- السجلات -----
@app.route('/api/logs')
@master_required
def get_logs_api():
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            return jsonify({'logs': f.read()[-50000:]})
    return jsonify({'logs': ''})

@app.route('/api/logs/clear', methods=['POST'])
@master_required
def clear_logs_api():
    with open(LOGS_FILE, 'w') as f:
        f.write(f"[{datetime.now()}] CLEARED\n")
    save_json_file(ACTIVITY_FILE, {'events': []})
    return jsonify({'success': True})

# ----- إعدادات المالك -----
@app.route('/api/master/change-username', methods=['POST'])
@master_required
def change_master_username_api():
    global MASTER_USERNAME
    MASTER_USERNAME = request.json['new_username']
    MASTER_CONFIG['master_username'] = MASTER_USERNAME
    save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
    return jsonify({'success': True})

@app.route('/api/master/change-password', methods=['POST'])
@master_required
def change_master_password_api():
    global MASTER_PASSWORD_HASH
    d = request.json
    if hashlib.sha256(d['current_password'].encode()).hexdigest() == MASTER_PASSWORD_HASH:
        MASTER_PASSWORD_HASH = hashlib.sha256(d['new_password'].encode()).hexdigest()
        MASTER_CONFIG['master_password_hash'] = MASTER_PASSWORD_HASH
        save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/master/change-port', methods=['POST'])
@master_required
def change_port_api():
    try:
        port = int((request.json or {}).get('port', 3177))
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid port'})
    MASTER_CONFIG['port'] = port
    save_json_file(MASTER_CONFIG_FILE, MASTER_CONFIG)
    threading.Thread(target=lambda: (time.sleep(1), os.execv(sys.executable, [sys.executable] + sys.argv))).start()
    return jsonify({'success': True})

@app.route('/api/master/restart', methods=['POST'])
@master_required
def restart_panel_api():
    log_activity(session['username'], 'server.power.restart', 'Panel restart requested')
    threading.Thread(target=lambda: (time.sleep(1), os.execv(sys.executable, [sys.executable] + sys.argv))).start()
    return jsonify({'success': True})


# =============================================================================
# 15)  API routes قسم المالك (Owner Panel)
# =============================================================================

@app.route('/api/owner/config')
@master_required
def owner_config_get():
    cfg = load_owner_config()
    # لا نرسل التوكن كاملاً للأمان
    safe = dict(cfg)
    safe['telegram_token'] = '***' if cfg.get('telegram_token') else ''
    return jsonify(safe)

@app.route('/api/owner/config/save', methods=['POST'])
@master_required
def owner_config_save():
    d = request.json or {}
    cfg = load_owner_config()
    if 'panel_name' in d:
        cfg['panel_name'] = d['panel_name']
    if 'welcome_msg' in d:
        cfg['welcome_msg'] = d['welcome_msg']
    save_json_file(OWNER_CONFIG_FILE, cfg)
    log_activity(session['username'], 'owner.config.save', 'Panel settings updated')
    return jsonify({'success': True})

@app.route('/api/owner/maintenance', methods=['GET', 'POST'])
@login_required
def owner_maintenance_api():
    if request.method == 'GET':
        return jsonify(load_maintenance())
    if session.get('username') != MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Master only'}), 403
    d = request.json or {}
    maint = load_maintenance()
    if 'enabled' in d:
        maint['enabled'] = bool(d['enabled'])
    if 'message' in d:
        maint['message'] = d['message']
    save_maintenance(maint)
    log_activity(session['username'], 'owner.maintenance', 'enabled='+str(maint['enabled']))
    return jsonify({'success': True, 'enabled': maint['enabled']})

@app.route('/api/owner/stats')
@master_required
def owner_stats_api():
    users = load_users()
    # عد ملفات ZIP في جميع مجلدات المستخدمين
    zip_count = 0
    try:
        for root, dirs, files in os.walk(USERS_FOLDER):
            for f in files:
                if f.lower().endswith('.zip'):
                    zip_count += 1
        # أيضاً في مجلد BASE_PATH
        for f in os.listdir(BASE_PATH):
            if f.lower().endswith('.zip'):
                zip_count += 1
    except Exception:
        pass
    # عد البوتات النشطة
    active_bots = sum(1 for p in file_processes.values() if p['process'].poll() is None)
    # تحديث الإحصائيات
    stats = {
        'total_users': len(users),
        'total_servers': len(users),
        'active_bots': active_bots,
        'zip_files': zip_count,
        'last_updated': datetime.now().isoformat()
    }
    save_json_file(BOT_STATS_FILE, stats)
    return jsonify(stats)

@app.route('/api/owner/bot/link', methods=['POST'])
@master_required
def owner_bot_link():
    d = request.json or {}
    token = d.get('token', '').strip()
    owner_id = d.get('owner_id', '').strip()
    if not token or not owner_id:
        return jsonify({'success': False, 'error': 'Token and owner ID required'})
    # التحقق من صحة التوكن عبر Telegram API
    try:
        resp = requests.get(f'https://api.telegram.org/bot{token}/getMe', timeout=10)
        data = resp.json()
        if not data.get('ok'):
            return jsonify({'success': False, 'error': data.get('description', 'Invalid token')})
        bot_username = data['result'].get('username', 'unknown')
        cfg = load_owner_config()
        cfg['telegram_token'] = token
        cfg['telegram_owner_id'] = owner_id
        cfg['bot_linked'] = True
        cfg['bot_username'] = bot_username
        save_json_file(OWNER_CONFIG_FILE, cfg)
        log_activity(session['username'], 'owner.bot.link', f'Bot @{bot_username} linked')
        return jsonify({'success': True, 'bot_username': bot_username})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/owner/bot/unlink', methods=['POST'])
@master_required
def owner_bot_unlink():
    cfg = load_owner_config()
    cfg['telegram_token'] = ''
    cfg['telegram_owner_id'] = ''
    cfg['bot_linked'] = False
    cfg['bot_username'] = ''
    save_json_file(OWNER_CONFIG_FILE, cfg)
    log_activity(session['username'], 'owner.bot.unlink', 'Bot unlinked')
    return jsonify({'success': True})

@app.route('/api/owner/bot/action', methods=['POST'])
@master_required
def owner_bot_action():
    # تحقق من أن المستخدم هو المالك فقط
    if session.get('username') != MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Unauthorized: Master only'}), 403
    d = request.json or {}
    action = d.get('action', '')
    cfg = load_owner_config()
    if not cfg.get('bot_linked') or not cfg.get('telegram_token'):
        return jsonify({'success': False, 'error': 'Bot not linked'}), 403
    token = cfg['telegram_token']
    owner_id = cfg['telegram_owner_id']
    messages = {
        'start': '✅ Bot started via panel',
        'stop': '⏹ Bot stopped via panel',
        'restart': '🔄 Bot restarted via panel'
    }
    msg = messages.get(action, f'Action: {action}')
    # إضافة أزرار شفافة (Inline Keyboard)
    keyboard = {
        'inline_keyboard': [
            [{'text': '🔄 Restart', 'callback_data': 'restart'}, {'text': '⏹ Stop', 'callback_data': 'stop'}],
            [{'text': '📊 Stats', 'callback_data': 'stats'}, {'text': '🌐 Open Panel', 'url': request.host_url}]
        ]
    }
    try:
        requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                      json={'chat_id': owner_id, 'text': msg, 'reply_markup': keyboard}, timeout=10)
        log_activity(session['username'], f'owner.bot.{action}', msg)
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/owner/bot/cmd', methods=['POST'])
@master_required
def owner_bot_cmd():
    # تحقق من أن المستخدم هو المالك فقط
    if session.get('username') != MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Unauthorized: Master only'}), 403
    d = request.json or {}
    cmd = d.get('command', '').strip()
    cfg = load_owner_config()
    if not cfg.get('bot_linked'):
        return jsonify({'success': False, 'error': 'Bot not linked'}), 403
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = r.stdout + r.stderr
        # إرسال النتيجة عبر تيليجرام
        token = cfg['telegram_token']
        owner_id = cfg['telegram_owner_id']
        requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                      json={'chat_id': owner_id, 'text': f'🖥 CMD: {cmd}\n📝 Output:\n{output[:3000]}'}, timeout=10)
        log_activity(session['username'], 'owner.bot.cmd', cmd[:100])
        return jsonify({'success': True, 'output': output})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/owner/zips')
@master_required
def owner_list_zips():
    zips = []
    try:
        # مجلد المستخدمين
        for user_dir in os.listdir(USERS_FOLDER):
            user_path = os.path.join(USERS_FOLDER, user_dir)
            if os.path.isdir(user_path):
                for root, dirs, files in os.walk(user_path):
                    for f in files:
                        if f.lower().endswith('.zip'):
                            fp = os.path.join(root, f)
                            zips.append({
                                'name': f,
                                'user': user_dir,
                                'path': fp,
                                'size': f"{os.path.getsize(fp)/1024:.1f} KB"
                            })
        # مجلد BASE_PATH
        for f in os.listdir(BASE_PATH):
            if f.lower().endswith('.zip'):
                fp = os.path.join(BASE_PATH, f)
                zips.append({'name': f, 'user': 'master', 'path': fp, 'size': f"{os.path.getsize(fp)/1024:.1f} KB"})
    except Exception:
        pass
    return jsonify({'zips': zips})

@app.route('/api/owner/zips/download')
@master_required
def owner_download_zip():
    path = request.args.get('path', '')
    if not path or not os.path.exists(path):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    return send_file(path, as_attachment=True)

@app.route('/api/owner/zips/download-all')
@master_required
def owner_download_all_zips():
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        try:
            for user_dir in os.listdir(USERS_FOLDER):
                user_path = os.path.join(USERS_FOLDER, user_dir)
                if os.path.isdir(user_path):
                    for root, dirs, files in os.walk(user_path):
                        for f in files:
                            if f.lower().endswith('.zip'):
                                fp = os.path.join(root, f)
                                zf.write(fp, os.path.join(user_dir, f))
            for f in os.listdir(BASE_PATH):
                if f.lower().endswith('.zip'):
                    fp = os.path.join(BASE_PATH, f)
                    zf.write(fp, os.path.join('master', f))
        except Exception:
            pass
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='all_zips.zip', mimetype='application/zip')

@app.route('/api/owner/zips/delete', methods=['POST'])
@master_required
def owner_delete_zip():
    path = (request.json or {}).get('path', '')
    if not path or not os.path.exists(path):
        return jsonify({'success': False, 'error': 'File not found'})
    try:
        os.remove(path)
        log_activity(session['username'], 'owner.zip.delete', path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/owner/announcements')
@login_required
def owner_get_announcements():
    return jsonify(load_announcements())

@app.route('/api/owner/announcements/add', methods=['POST'])
@master_required
def owner_add_announcement():
    d = request.json or {}
    text = d.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'error': 'Empty text'})
    data = load_announcements()
    data['list'].insert(0, {'text': text, 'time': datetime.now().strftime('%Y-%m-%d %H:%M')})
    data['list'] = data['list'][:50]  # احتفظ بآخر 50
    save_announcements(data)
    log_activity(session['username'], 'owner.announce.add', text[:80])
    return jsonify({'success': True})

@app.route('/api/owner/announcements/delete', methods=['POST'])
@master_required
def owner_delete_announcement():
    d = request.json or {}
    idx = d.get('index', -1)
    data = load_announcements()
    try:
        data['list'].pop(int(idx))
        save_announcements(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/owner/broadcast', methods=['POST'])
@master_required
def owner_broadcast():
    d = request.json or {}
    msg = d.get('message', '').strip()
    if not msg:
        return jsonify({'success': False, 'error': 'Empty message'})
    cfg = load_owner_config()
    users = load_users()
    count = 0
    if cfg.get('bot_linked') and cfg.get('telegram_token'):
        token = cfg['telegram_token']
        # إرسال للمالك أولاً
        try:
            requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                          json={'chat_id': cfg['telegram_owner_id'], 'text': f'📡 Broadcast:\n{msg}'}, timeout=10)
            count += 1
        except Exception:
            pass
    # تسجيل الإعلان أيضاً
    data = load_announcements()
    data['list'].insert(0, {'text': f'[BROADCAST] {msg}', 'time': datetime.now().strftime('%Y-%m-%d %H:%M')})
    save_announcements(data)
    log_activity(session['username'], 'owner.broadcast', msg[:80])
    return jsonify({'success': True, 'count': count})

@app.route('/api/owner/action', methods=['POST'])
@master_required
def owner_action_api():
    action = (request.json or {}).get('action', '')
    try:
        if action == 'clear_all_logs':
            with open(LOGS_FILE, 'w') as f:
                f.write(f"[{datetime.now()}] CLEARED BY OWNER\n")
            save_json_file(ACTIVITY_FILE, {'events': []})
        elif action == 'kick_all_users':
            sessions = load_user_sessions()
            for u in list(sessions.keys()):
                if u != MASTER_USERNAME:
                    sessions[u] = 0
            save_user_sessions(sessions)
        elif action == 'reset_stats':
            save_json_file(BOT_STATS_FILE, {'total_users': 0, 'total_servers': 0, 'active_bots': 0, 'zip_files': 0, 'last_updated': ''})
        elif action == 'restart_panel':
            threading.Thread(target=lambda: (time.sleep(1), os.execv(sys.executable, [sys.executable] + sys.argv))).start()
        log_activity(session['username'], f'owner.action.{action}', '')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/owner/kick-user', methods=['POST'])
@master_required
def owner_kick_user():
    username = (request.json or {}).get('username', '')
    if not username or username == MASTER_USERNAME:
        return jsonify({'success': False, 'error': 'Invalid username'})
    try:
        sessions = load_user_sessions()
        sessions[username] = 0
        save_user_sessions(sessions)
        log_activity(session['username'], 'owner.kick_user', username)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ─── إعدادات قناة الإثبات ──────────────────────────────────────────────────
@app.route('/api/owner/proof-channel', methods=['GET', 'POST'])
@master_required
def proof_channel_api():
    bot_db_path = os.path.join(BASE_PATH, 'panel_data', 'bot_data.db')
    def _get_setting(key):
        try:
            import sqlite3 as _sq
            conn = _sq.connect(bot_db_path)
            row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            conn.close()
            return row[0] if row else ''
        except Exception:
            return ''
    def _update_setting(key, value):
        try:
            import sqlite3 as _sq
            conn = _sq.connect(bot_db_path)
            conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            conn.commit()
            conn.close()
        except Exception as e:
            raise e
    if request.method == 'GET':
        return jsonify({'channel': _get_setting('proof_channel'), 'success': True})
    d = request.json or {}
    _update_setting('proof_channel', d.get('channel', ''))
    log_activity(session['username'], 'owner.proof_channel.update', d.get('channel',''))
    return jsonify({'success': True})

# ─── إعدادات دفع النجوم ──────────────────────────────────────────────────────
@app.route('/api/owner/star-payment', methods=['GET', 'POST'])
@master_required
def star_payment_api():
    bot_db_path = os.path.join(BASE_PATH, 'panel_data', 'bot_data.db')
    def _get_setting(key):
        try:
            import sqlite3 as _sq
            conn = _sq.connect(bot_db_path)
            row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            conn.close()
            return row[0] if row else ''
        except Exception:
            return ''
    def _update_setting(key, value):
        try:
            import sqlite3 as _sq
            conn = _sq.connect(bot_db_path)
            conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            conn.commit()
            conn.close()
        except Exception:
            pass
    if request.method == 'GET':
        return jsonify({
            'price': _get_setting('star_price') or '1',
            'label': _get_setting('star_amount_label') or 'دعم بنجمة',
            'success': True
        })
    d = request.json or {}
    if 'price' in d:
        _update_setting('star_price', str(d['price']))
    if 'label' in d:
        _update_setting('star_amount_label', d['label'])
    log_activity(session['username'], 'owner.star_payment.update', '')
    return jsonify({'success': True})

# ─── قفل/فتح البوت ────────────────────────────────────────────────────────────
@app.route('/api/owner/bot-lock', methods=['GET', 'POST'])
@master_required
def bot_lock_api():
    bot_db_path = os.path.join(BASE_PATH, 'panel_data', 'bot_data.db')
    def _get_setting(key):
        try:
            import sqlite3 as _sq
            conn = _sq.connect(bot_db_path)
            row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            conn.close()
            return row[0] if row else ''
        except Exception:
            return ''
    def _update_setting(key, value):
        try:
            import sqlite3 as _sq
            conn = _sq.connect(bot_db_path)
            conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            conn.commit()
            conn.close()
        except Exception:
            pass
    if request.method == 'GET':
        return jsonify({
            'locked': _get_setting('bot_locked') == '1',
            'message': _get_setting('bot_lock_msg') or 'البوت في وضع الصيانة مؤقتاً 🔧',
            'success': True
        })
    d = request.json or {}
    if 'locked' in d:
        _update_setting('bot_locked', '1' if d['locked'] else '0')
    if 'message' in d:
        _update_setting('bot_lock_msg', d['message'])
    action = 'locked' if d.get('locked') else 'unlocked'
    log_activity(session['username'], f'owner.bot.{action}', '')
    return jsonify({'success': True})

# ─── تذاكر الدعم الفني ────────────────────────────────────────────────────────
@app.route('/api/owner/support-tickets', methods=['GET'])
@master_required
def support_tickets_api():
    tickets_file = os.path.join(BASE_PATH, 'panel_data', 'support_tickets.json')
    try:
        with open(tickets_file, 'r', encoding='utf-8') as f:
            tickets = json.load(f)
    except Exception:
        tickets = {}
    return jsonify({'tickets': tickets, 'success': True})

# =============================================================================
# 14)  ميزة Multi-Port: تشغيل Sub-servers على بورتات إضافية
# =============================================================================
def run_extra_port(port, note=""):
    """يشغل Flask sub-server على بورت إضافي يقدم نفس اللوحة."""
    try:
        from flask import Flask as _F
        sub = _F(f"sub_{port}")
        @sub.route('/')
        def _h():
            return f"<h1 style='font-family:sans-serif;color:#29c7d3;background:#1f2933;padding:40px;text-align:center'>PANELVEEX — Port {port}</h1><p style='color:#9aa9b3;text-align:center'>{html.escape(note)}</p><p style='text-align:center'><a style='color:#2f6fed' href='/'>Open user app here</a></p>"
        sub.run(host='0.0.0.0', port=port, debug=False, threaded=True, use_reloader=False)
    except Exception as e:
        print(f"[port {port}] failed: {e}")

def start_configured_extra_ports():
    for p in load_ports():
        try:
            threading.Thread(target=run_extra_port, args=(int(p['port']), p.get('note','')), daemon=True).start()
        except Exception:
            pass

# =============================================================================
# التشغيل الرئيسي
# =============================================================================
def run_telegram_bot():
    """يشغّل bot.py كـ subprocess مستقل — يعيد المحاولة عند الانهيار"""
    # يمكن تعطيله بـ  RUN_BOT=0  في متغيرات البيئة
    if os.environ.get("RUN_BOT", "1") == "0":
        print(" * [BOT] disabled via RUN_BOT=0")
        return
    bot_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot.py')
    if not os.path.exists(bot_script):
        print(f" * [BOT] not found: {bot_script}")
        return
    print(f" * [BOT] starting: {bot_script}")
    while True:
        try:
            proc = subprocess.Popen(
                [sys.executable, bot_script],
                cwd=os.path.dirname(bot_script),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            for line in proc.stdout:
                print("[BOT]", line.decode(errors='replace').rstrip())
            proc.wait()
            print(" * [BOT] process ended — restarting in 5s...")
        except Exception as e:
            print(f" * [BOT] error: {e} — restarting in 5s...")
        time.sleep(5)

# ─── الدالة القديمة للبوت (محذوفة - استُبدلت بـ bot.py) ────────────────────
def _old_bot_placeholder():
    try:
        import telebot
        from telebot import types
        import hashlib
        from datetime import datetime, timedelta
        
        cfg = load_owner_config()
        TOKEN = cfg.get('telegram_token', '')
        ADMIN_ID = int(cfg.get('telegram_owner_id', 0))
        if not TOKEN:
            print(" * Telegram Bot: no token configured, skipping.")
            return
        bot = telebot.TeleBot(TOKEN)

        # إعدادات البوت (تُحفظ في ملف منفصل)
        BOT_SETTINGS_FILE = os.path.join(BASE_PATH, 'bot_settings.json')
        def load_bot_settings():
            return load_json_file(BOT_SETTINGS_FILE, {
                'force_channel': '@V_P1_V1',
                'force_channel2': '@VSA_A',
                'points_per_server': 10,
                'points_per_invite': 2,
                'dev_channel': 'https://t.me/V_P1_V1',
                'dev_user': 'https://t.me/V2X_2',
                'admin_list': [],
                'codes': {},
                'panel_url': ''
            })
        
        def save_bot_settings(s):
            save_json_file(BOT_SETTINGS_FILE, s)

        def check_force_subscribe(user_id):
            settings = load_bot_settings()
            channels = [
                settings.get('force_channel', '').strip(),
                settings.get('force_channel2', '').strip(),
            ]
            channels = [c for c in channels if c]
            if not channels: return True
            for channel in channels:
                try:
                    member = bot.get_chat_member(channel, user_id)
                    if member.status not in ['member', 'administrator', 'creator']:
                        return False
                except Exception:
                    return False
            return True

        def enforce_subscription(message):
            """فحص الاشتراك الإجباري في قناتين وإرسال رسالة التنبيه. يرجع True إذا مسموح."""
            settings = load_bot_settings()
            channels = [
                settings.get('force_channel', '').strip(),
                settings.get('force_channel2', '').strip(),
            ]
            channels = [c for c in channels if c]
            if not channels:
                return True
            unsubscribed = []
            for channel in channels:
                try:
                    member = bot.get_chat_member(channel, message.from_user.id)
                    if member.status not in ['member', 'administrator', 'creator']:
                        unsubscribed.append(channel)
                except Exception:
                    unsubscribed.append(channel)
            if not unsubscribed:
                return True
            sep = "\u200B\n"
            prompt = (
                ">⛔ عـذراً\!\n" + sep +
                ">لا يمكنك استخدام البوت قبل الاشتراك في القنوات\n" + sep +
                ">اشترك في القنوات ثم اضغط زر **تحققت من الاشتراك** 👇"
            )
            mk = types.InlineKeyboardMarkup(row_width=1)
            for channel in unsubscribed:
                chan_link = channel if channel.startswith('http') else f"https://t.me/{channel.lstrip('@')}"
                chan_name = channel.lstrip('@').replace('https://t.me/', '')
                mk.add(types.InlineKeyboardButton(f"🔔 اشترك في {chan_name}", url=chan_link))
            mk.add(types.InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_sub_verify"))
            bot.send_message(message.chat.id, prompt, parse_mode="MarkdownV2", reply_markup=mk)
            return False

        def is_admin(user_id):
            if user_id == ADMIN_ID: return True
            settings = load_bot_settings()
            return user_id in settings.get('admin_list', [])

        # الكيبوردات
        def main_keyboard(user_id):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.row("ملفي الشخصي")
            markup.row("إنشاء سيرفر", "شراء نقاط")
            markup.row("استخدام كود")
            markup.row("مساعدة", "إحالة")
            markup.row("المطور", "قناة المطور")
            if is_admin(user_id):
                markup.row("لوحة الأدمن")
            return markup

        def admin_keyboard():
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("إحصائيات", callback_data="admin_stats"),
                types.InlineKeyboardButton("فحص مستخدم", callback_data="admin_check_user"),
                types.InlineKeyboardButton("حظر مستخدم", callback_data="admin_ban"),
                types.InlineKeyboardButton("فك حظر", callback_data="admin_unban"),
                types.InlineKeyboardButton("إضافة أدمن", callback_data="admin_add_admin"),
                types.InlineKeyboardButton("حذف أدمن", callback_data="admin_del_admin"),
                types.InlineKeyboardButton("إضافة قناة إجبارية", callback_data="admin_add_channel"),
                types.InlineKeyboardButton("حذف قناة إجبارية", callback_data="admin_del_channel"),
                types.InlineKeyboardButton("إضافة كود", callback_data="admin_add_code"),
                types.InlineKeyboardButton("قائمة الأكواد", callback_data="admin_list_codes"),
                types.InlineKeyboardButton("قائمة السيرفرات", callback_data="admin_list_servers"),
                types.InlineKeyboardButton("إضافة نقاط", callback_data="admin_add_points"),
                types.InlineKeyboardButton("خصم نقاط", callback_data="admin_del_points"),
                types.InlineKeyboardButton("تكلفة السيرفر (نقاط)", callback_data="admin_set_server_cost"),
                types.InlineKeyboardButton("تعيين لينك اللوحة", callback_data="admin_set_panel_url")
            )
            return markup

        @bot.message_handler(commands=['start'])
        def start(message):
            if not enforce_subscription(message):
                return
            
            # منطق النقاط عند الدخول عبر رابط دعوة
            args = message.text.split()
            if len(args) > 1:
                inviter_id = int(args[1])
                if inviter_id != message.from_user.id:
                    users = load_users()
                    for u, data in users.items():
                        if data.get('telegram_id') == inviter_id:
                            settings = load_bot_settings()
                            data['points'] = data.get('points', 0) + settings.get('points_per_invite', 2)
                            save_users(users)
                            try:
                                bot.send_message(inviter_id, f"💰 لقد حصلت على {settings.get('points_per_invite', 2)} نقاط لأن صديقك اشترك عبر رابطك!")
                            except: pass
                            break
            
            first_name = message.from_user.first_name or "مستخدم"
            sep = "\u200B\n"
            welcome_caption = (
                ">أهـلاً بـك 𝗩𝗘𝗫 \\| فيكس فـي بـوت VEX  VPS\n" + sep +
                ">هنـا تجـد سيـرفرات VPS بلـغـه بـايثـون\n" + sep +
                ">مميـزاتـنا  :\n" + sep +
                ">عـزل آمـن بيـن السـيرفـرات\n" + sep +
                ">حـمايـه قـويه ضـد الهجـمات\n" + sep +
                ">سـهـوله التحـكم فـي ملفـاتك\n" + sep +
                ">اسـتقـرار النـظام الـدائــم\n" + sep +
                ">مـراقـبه الشبـكه و حـمايه المـلفات من أي هجـمات\n" + sep +
                ">عـمل دائـم بـدون تـوقف أبـداً\n" + sep +
                ">*قـم بـالبــدء الآن نحـو القـمه*"
            )
            bot.send_photo(
                message.chat.id,
                photo="https://g.top4top.io/p_3832nmswi0.jpg",
                caption=welcome_caption,
                parse_mode="MarkdownV2",
                reply_markup=main_keyboard(message.from_user.id)
            )

        @bot.message_handler(func=lambda m: m.text == "ملفي الشخصي")
        def my_info(message):
            if not enforce_subscription(message): return
            users = load_users()
            ips_data = load_ips()
            assigned_ips = ips_data.get('assigned', {})

            # جمع كل السيرفرات (الحسابات) المرتبطة بهذا المستخدم
            my_servers = []
            for u, data in users.items():
                if data.get('telegram_id') == message.from_user.id:
                    my_servers.append((u, data))

            if not my_servers:
                bot.send_message(message.chat.id, "❌ لم يتم العثور على حساب مرتبط بهذا التليجرام.\nقم بإنشاء حساب أولاً.")
                return

            settings = load_bot_settings()
            panel_url = settings.get('panel_url', '').strip()

            # أول حساب = البيانات الأساسية للمستخدم
            first_uname, first_data = my_servers[0]
            msg = f"👤 **ملفك الشخصي:**\n\n"
            msg += f"💰 النقاط: `{first_data.get('points', 0)}` نقطة\n"
            msg += f"🖥️ السيرفرات المتاحة: `{first_data.get('max_servers', 2)}`\n"
            msg += f"📅 تاريخ الإنشاء: `{first_data.get('created', '-')[:10]}`\n\n"
            msg += f"━━━━━━━━━━━━━━━━━━\n"
            msg += f"🖥️ **سيرفراتك ({len(my_servers)}):**\n\n"

            for idx, (uname, data) in enumerate(my_servers, 1):
                ip = assigned_ips.get(uname, 'غير متاح')
                password = data.get('password_plain', '🔒 مشفرة')
                msg += f"**السيرفر {idx}:**\n"
                msg += f"  👤 المستخدم: `{uname}`\n"
                msg += f"  🔑 كلمة السر: `{password}`\n"
                msg += f"  🌐 الـ IP: `{ip}`\n\n"

            mk = types.InlineKeyboardMarkup()
            if panel_url:
                mk.add(types.InlineKeyboardButton("🌐 لوحة التحكم", url=panel_url))
            bot.send_message(message.chat.id, msg, parse_mode="Markdown",
                             reply_markup=mk if panel_url else None)

        @bot.message_handler(func=lambda m: m.text == "إنشاء سيرفر")
        def create_account_start(message):
            if not enforce_subscription(message): return
            users = load_users()
            user_data = None
            uname = None
            for u, data in users.items():
                if data.get('telegram_id') == message.from_user.id:
                    user_data = data
                    uname = u
                    break
            if user_data:
                settings = load_bot_settings()
                cost = settings.get('points_per_server', 5)
                pts = user_data.get('points', 0)
                max_srv = user_data.get('max_servers', 1)
                mk = types.InlineKeyboardMarkup(row_width=1)
                mk.add(types.InlineKeyboardButton(
                    f"🖥️ شراء سيرفر إضافي ({cost} نقطة) — رصيدك: {pts} نقطة",
                    callback_data="buy_server_slot"
                ))
                bot.send_message(message.chat.id,
                    f"✅ لديك حساب بالفعل!\n\n"
                    f"👤 المستخدم: `{uname}`\n"
                    f"🖥️ سيرفراتك المتاحة: `{max_srv}`\n"
                    f"💰 رصيدك: `{pts}` نقطة\n\n"
                    f"يمكنك زيادة عدد سيرفراتك بشراء سيرفر إضافي مقابل {cost} نقطة:",
                    parse_mode="Markdown", reply_markup=mk)
                return
            msg = bot.send_message(message.chat.id, "🚀 أرسل اسم المستخدم الذي تريده (باللغة الإنجليزية):")
            bot.register_next_step_handler(msg, process_username)

        def process_username(message):
            if not enforce_subscription(message): return
            username = message.text.strip()
            if not username or not username.isalnum():
                bot.send_message(message.chat.id, "❌ اسم مستخدم غير صالح! استخدم أحرف وأرقام فقط.")
                return
            
            users = load_users()
            if username in users:
                bot.send_message(message.chat.id, "❌ اسم المستخدم هذا مأخوذ بالفعل.")
                return
            
            msg = bot.send_message(message.chat.id, "ارسل كلمة المرور التي تريدها:")
            bot.register_next_step_handler(msg, lambda m: process_password(m, username))

        def process_password(message, username):
            if not enforce_subscription(message): return
            password = message.text.strip()
            if len(password) < 6:
                bot.send_message(message.chat.id, "❌ كلمة المرور يجب أن تكون 6 أحرف على الأقل.")
                return
            
            users = load_users()
            users[username] = {
                'password': hashlib.sha256(password.encode()).hexdigest(),
                'password_plain': password, # لحفظها للمستخدم لرؤيتها لاحقاً
                'max_sessions': 999,
                'max_servers': 2,
                'points': 0,
                'main_file': 'main.py',
                'created': datetime.now().isoformat(),
                'expiry': None,
                'telegram_id': message.from_user.id,
                'banned': False
            }
            save_users(users)
            os.makedirs(os.path.join(USERS_FOLDER, username), exist_ok=True)
            assigned_ip = assign_ip(username)
            settings = load_bot_settings()
            panel_url = settings.get('panel_url', '').strip()
            first_name = message.from_user.first_name or username
            ip_str = escape_md2(assigned_ip or 'غير متاح')
            uname_str = escape_md2(username)
            pass_str = escape_md2(password)
            caption = (
                f">تـم إنشـاء السـيـرفر بـنجـاح  💫\n"
                f">\n"
                f">🌐 الـ IP  :  `{ip_str}`\n"
                f">إسم المسـتخدم  :  `{uname_str}`\n"
                f">كلـمـة المـرور  :  `{pass_str}`"
            )
            markup_photo = types.InlineKeyboardMarkup()
            if panel_url:
                markup_photo.add(types.InlineKeyboardButton("🌐 لوحة التحكم", url=panel_url))
            bot.send_photo(
                message.chat.id,
                photo="https://g.top4top.io/p_3832nmswi0.jpg",
                caption=caption,
                parse_mode="MarkdownV2",
                reply_markup=markup_photo if panel_url else None
            )

        @bot.message_handler(func=lambda m: m.text == "قناة المطور")
        def dev_channel_btn(message):
            if not enforce_subscription(message): return
            bot.send_message(message.chat.id, "📢 قناة المطور الرسمية:",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 انضم للقناة", url="https://t.me/V_P1_V1")
                ))

        @bot.message_handler(func=lambda m: m.text == "المطور")
        def dev_user_btn(message):
            if not enforce_subscription(message): return
            bot.send_message(message.chat.id, "👨‍💻 مطور البوت:",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("💬 تواصل مع المطور", url="https://t.me/V2X_2")
                ))

        @bot.callback_query_handler(func=lambda call: call.data == "check_sub_verify")
        def check_sub_verify(call):
            bot.answer_callback_query(call.id)
            settings = load_bot_settings()
            channels = [
                settings.get('force_channel', '').strip(),
                settings.get('force_channel2', '').strip(),
            ]
            channels = [c for c in channels if c]
            unsubscribed = []
            for channel in channels:
                try:
                    member = bot.get_chat_member(channel, call.from_user.id)
                    if member.status not in ['member', 'administrator', 'creator']:
                        unsubscribed.append(channel)
                except:
                    pass

            if not unsubscribed:
                pass  # تم التحقق - يكمل الكود بعدها
            else:
                sep = "\u200B\n"
                prompt = (
                    ">❌ لم يتم التحقق من اشتراكك بعد\!\n" + sep +
                    ">تأكد أنك اشتركت في جميع القنوات ثم اضغط التحقق مجدداً 👇"
                )
                mk = types.InlineKeyboardMarkup(row_width=1)
                for channel in unsubscribed:
                    chan_link = channel if channel.startswith('http') else f"https://t.me/{channel.lstrip('@')}"
                    chan_name = channel.lstrip('@').replace('https://t.me/', '')
                    mk.add(types.InlineKeyboardButton(f"🔔 اشترك في {chan_name}", url=chan_link))
                mk.add(types.InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_sub_verify"))
                try:
                    bot.edit_message_text(prompt, call.message.chat.id, call.message.message_id,
                                          parse_mode="MarkdownV2", reply_markup=mk)
                except:
                    bot.send_message(call.message.chat.id, prompt, parse_mode="MarkdownV2", reply_markup=mk)
                return

            # مشترك ✅ — احذف رسالة الاشتراك وابعت رسالة الترحيب
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass

            sep = "\u200B\n"
            welcome_caption = (
                ">أهـلاً بـك 𝗩𝗘𝗫 \\| فيكس فـي بـوت VEX  VPS\n" + sep +
                ">هنـا تجـد سيـرفرات VPS بلـغـه بـايثـون\n" + sep +
                ">مميـزاتـنا  :\n" + sep +
                ">عـزل آمـن بيـن السـيرفـرات\n" + sep +
                ">حـمايـه قـويه ضـد الهجـمات\n" + sep +
                ">سـهـوله التحـكم فـي ملفـاتك\n" + sep +
                ">اسـتقـرار النـظام الـدائــم\n" + sep +
                ">مـراقـبه الشبـكه و حـمايه المـلفات من أي هجـمات\n" + sep +
                ">عـمل دائـم بـدون تـوقف أبـداً\n" + sep +
                ">*قـم بـالبــدء الآن نحـو القـمه*"
            )
            bot.send_photo(
                call.message.chat.id,
                photo="https://g.top4top.io/p_3832nmswi0.jpg",
                caption=welcome_caption,
                parse_mode="MarkdownV2",
                reply_markup=main_keyboard(call.from_user.id)
            )

        @bot.callback_query_handler(func=lambda call: call.data == "buy_server_slot")
        def buy_server_slot(call):
            bot.answer_callback_query(call.id)
            users = load_users()
            settings = load_bot_settings()
            cost = settings.get('points_per_server', 10)
            for uname, data in users.items():
                if data.get('telegram_id') == call.from_user.id:
                    pts = data.get('points', 0)
                    if pts < cost:
                        bot.send_message(call.message.chat.id,
                            f"❌ رصيدك غير كافٍ!\n\n"
                            f"💰 رصيدك: `{pts}` نقطة\n"
                            f"💸 المطلوب: `{cost}` نقطة\n\n"
                            f"استخدم رابط الإحالة 🔗 أو الأكواد 🎟️ للحصول على نقاط.",
                            parse_mode="Markdown")
                        return
                    # خصم النقاط مؤقتاً وابدأ تسجيل سيرفر جديد
                    data['points'] = pts - cost
                    save_users(users)
                    bot.send_message(call.message.chat.id,
                        f"✅ تم خصم `{cost}` نقطة.\n\n🖥️ الآن أنشئ سيرفرك الجديد:\nأرسل اسم المستخدم الجديد (باللغة الإنجليزية):",
                        parse_mode="Markdown")
                    msg = bot.send_message(call.message.chat.id, "اكتب اسم المستخدم:")
                    bot.register_next_step_handler(msg, process_paid_username)
                    return
            bot.send_message(call.message.chat.id, "❌ لم يتم العثور على حسابك.")

        def process_paid_username(message):
            if not enforce_subscription(message): return
            username = message.text.strip()
            if not username or not username.isalnum():
                bot.send_message(message.chat.id, "❌ اسم مستخدم غير صالح! استخدم أحرف وأرقام فقط.")
                return
            users = load_users()
            if username in users:
                bot.send_message(message.chat.id, "❌ اسم المستخدم هذا مأخوذ. اختر اسماً آخر:")
                msg = bot.send_message(message.chat.id, "اكتب اسم المستخدم:")
                bot.register_next_step_handler(msg, process_paid_username)
                return
            msg = bot.send_message(message.chat.id, f"👤 اسم المستخدم: `{username}`\n\nأرسل كلمة المرور:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: process_paid_password(m, username))

        def process_paid_password(message, username):
            if not enforce_subscription(message): return
            password = message.text.strip()
            if len(password) < 6:
                bot.send_message(message.chat.id, "❌ كلمة المرور يجب أن تكون 6 أحرف على الأقل.")
                return
            users = load_users()
            users[username] = {
                'password': hashlib.sha256(password.encode()).hexdigest(),
                'password_plain': password,
                'max_sessions': 999,
                'max_servers': 2,
                'points': 0,
                'main_file': 'main.py',
                'created': datetime.now().isoformat(),
                'expiry': None,
                'telegram_id': message.from_user.id,
                'banned': False
            }
            save_users(users)
            os.makedirs(os.path.join(USERS_FOLDER, username), exist_ok=True)
            assigned_ip = assign_ip(username)
            settings = load_bot_settings()
            panel_url = settings.get('panel_url', '').strip()
            first_name = message.from_user.first_name or username
            ip_str = escape_md2(assigned_ip or 'غير متاح')
            uname_str = escape_md2(username)
            pass_str = escape_md2(password)
            caption = (
                f">تـم إنشـاء السـيـرفر بـنجـاح  💫\n"
                f">\n"
                f">🌐 الـ IP  :  `{ip_str}`\n"
                f">إسم المسـتخدم  :  `{uname_str}`\n"
                f">كلـمـة المـرور  :  `{pass_str}`"
            )
            markup_photo = types.InlineKeyboardMarkup()
            if panel_url:
                markup_photo.add(types.InlineKeyboardButton("🌐 لوحة التحكم", url=panel_url))
            bot.send_photo(
                message.chat.id,
                photo="https://g.top4top.io/p_3832nmswi0.jpg",
                caption=caption,
                parse_mode="MarkdownV2",
                reply_markup=markup_photo if panel_url else None
            )

        @bot.message_handler(func=lambda m: m.text == "إحالة")
        def invite_link(message):
            if not enforce_subscription(message): return
            link = f"https://t.me/{(bot.get_me().username)}?start={message.from_user.id}"
            settings = load_bot_settings()
            bot.send_message(message.chat.id, f"🔗 **رابط الإحالة الخاص بك:**\n\nشارك هذا الرابط مع أصدقائك:\n`{link}`\n\n💰 لكل شخص يشترك من خلالك ستحصل على *{settings.get('points_per_invite', 2)} نقاط*.\n\n🎁 يمكنك استبدال النقاط بزيادة عدد السيرفرات المتاحة لك.", parse_mode="Markdown")

        @bot.message_handler(func=lambda m: m.text == "شراء نقاط")
        def buy_points(message):
            if not enforce_subscription(message): return
            settings = load_bot_settings()
            bot.send_message(message.chat.id,
                f"💫 **شراء النقاط:**\n\n"
                f"🔹 {settings.get('points_per_server', 10)} نقطة = سيرفر إضافي\n"
                f"🔹 للحصول على نقاط مجانية استخدم زر الإحالة 🔗\n\n"
                f"📩 للشراء تواصل مع المطور:",
                parse_mode="Markdown",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("👨‍💻 تواصل مع المطور", url=settings.get('dev_user', 'https://t.me/V2X_2'))
                )
            )

        @bot.message_handler(func=lambda m: m.text == "مساعدة")
        def help_msg(message):
            if not enforce_subscription(message): return
            settings = load_bot_settings()
            bot.send_message(message.chat.id,
                "❓ **المساعدة:**\n\n"
                "🚀 *إنشاء سيرفر* — أنشئ حساباً للوحة التحكم\n"
                "👤 *ملفي الشخصي* — عرض بياناتك وكلمة مرورك\n"
                "🔗 *إحالة* — احصل على نقاط بدعوة أصدقائك\n"
                "💫 *شراء نقاط* — زيادة عدد سيرفراتك\n"
                "🎟️ *استخدام كود* — استخدم كود للحصول على نقاط\n\n"
                "🌐 رابط لوحة التحكم:",
                parse_mode="Markdown",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 قناة المطور", url=settings.get('dev_channel', 'https://t.me/V_P1_V1'))
                )
            )

        @bot.message_handler(func=lambda m: m.text == "استخدام كود")
        def use_code(message):
            if not enforce_subscription(message): return
            msg = bot.send_message(message.chat.id, "🎟️ أرسل الكود الذي تريد استخدامه:")
            bot.register_next_step_handler(msg, process_code)

        def process_code(message):
            if not enforce_subscription(message): return
            code_input = message.text.strip()
            settings = load_bot_settings()
            codes = settings.get('codes', {})
            if code_input not in codes:
                bot.send_message(message.chat.id, "❌ الكود غير صحيح أو منتهي الصلاحية.")
                return
            code_data = codes[code_input]
            if code_data.get('uses', 0) <= 0:
                bot.send_message(message.chat.id, "❌ هذا الكود نفدت استخداماته.")
                return
            # فحص إذا المستخدم استخدمه من قبل
            used_by = code_data.get('used_by', [])
            if message.from_user.id in used_by:
                bot.send_message(message.chat.id, "❌ لقد استخدمت هذا الكود من قبل.")
                return
            # تطبيق النقاط
            users = load_users()
            found = False
            for u, data in users.items():
                if data.get('telegram_id') == message.from_user.id:
                    pts = code_data.get('points', 0)
                    data['points'] = data.get('points', 0) + pts
                    found = True
                    save_users(users)
                    # تحديث الكود
                    codes[code_input]['uses'] -= 1
                    codes[code_input].setdefault('used_by', []).append(message.from_user.id)
                    settings['codes'] = codes
                    save_bot_settings(settings)
                    bot.send_message(message.chat.id, f"✅ تم استخدام الكود بنجاح!\n💰 حصلت على *{pts} نقطة*!\n🔹 رصيدك الآن: *{data['points']} نقطة*", parse_mode="Markdown")
                    break
            if not found:
                bot.send_message(message.chat.id, "❌ لم يتم العثور على حسابك. قم بإنشاء حساب أولاً.")

        @bot.message_handler(func=lambda m: m.text == "📊 سيرفراتي")
        def my_servers(message):
            if not enforce_subscription(message): return
            procs = load_processes()
            users = load_users()
            uname = None
            for u, data in users.items():
                if data.get('telegram_id') == message.from_user.id:
                    uname = u
                    break
            
            if not uname:
                bot.send_message(message.chat.id, "❌ سجل أولاً.")
                return
            
            user_procs = [p for p in procs.values() if p.get('username') == uname]
            if not user_procs:
                bot.send_message(message.chat.id, "📭 ليس لديك سيرفرات شغالة حالياً.")
                return
            
            msg = "📊 **سيرفراتك الشغالة:**\n\n"
            for p in user_procs:
                msg += f"🔹 ملف: `{p.get('filename')}`\n"
                msg += f"🔹 PID: `{p.get('pid')}`\n"
                msg += f"🔹 الحالة: `Running`\n"
                msg += f"🔹 الوقت: `{p.get('start_time', '')[:19]}`\n\n"
            bot.send_message(message.chat.id, msg, parse_mode="Markdown")

        # لوحة الأدمن
        @bot.message_handler(func=lambda m: m.text == "لوحة الأدمن" and is_admin(m.from_user.id))
        def admin_panel(message):
            bot.send_message(message.chat.id, "👑 مرحباً بك في لوحة تحكم الأدمن:", reply_markup=admin_keyboard())

        @bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
        def admin_callbacks(call):
            if not is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية!")
                return
            bot.answer_callback_query(call.id)

            if call.data == "admin_stats":
                users = load_users()
                procs = load_processes()
                settings = load_bot_settings()
                admins = settings.get('admin_list', [])
                channel = settings.get('force_channel', 'غير محددة')
                msg = (f"📊 **إحصائيات النظام:**\n\n"
                       f"👥 عدد المستخدمين: `{len(users)}`\n"
                       f"🖥️ السيرفرات النشطة: `{len(procs)}`\n"
                       f"👑 الأدمنز: `{len(admins) + 1}`\n"
                       f"📢 قناة الاشتراك: `{channel}`\n"
                       f"💰 نقاط/سيرفر: `{settings.get('points_per_server', 10)}`\n"
                       f"🔗 نقاط/إحالة: `{settings.get('points_per_invite', 2)}`")
                bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

            elif call.data == "admin_ban":
                msg = bot.send_message(call.message.chat.id, "🚫 أرسل اسم المستخدم لحظره من البوت:")
                bot.register_next_step_handler(msg, admin_ban_user)

            elif call.data == "admin_unban":
                msg = bot.send_message(call.message.chat.id, "✅ أرسل اسم المستخدم لفك حظره:")
                bot.register_next_step_handler(msg, admin_unban_user)

            elif call.data == "admin_add_admin":
                msg = bot.send_message(call.message.chat.id, "➕ أرسل معرف التليجرام (ID) للمستخدم الجديد الأدمن:")
                bot.register_next_step_handler(msg, admin_add_admin_step)

            elif call.data == "admin_del_admin":
                settings = load_bot_settings()
                admins = settings.get('admin_list', [])
                if not admins:
                    bot.send_message(call.message.chat.id, "❌ لا يوجد أدمنز مضافون حالياً.")
                else:
                    bot.send_message(call.message.chat.id, f"👑 قائمة الأدمنز:\n" + "\n".join([f"• `{a}`" for a in admins]) + "\n\n➖ أرسل ID الأدمن لحذفه:", parse_mode="Markdown")
                    msg = bot.send_message(call.message.chat.id, "أرسل ID:")
                    bot.register_next_step_handler(msg, admin_del_admin_step)

            elif call.data == "admin_add_channel":
                msg = bot.send_message(call.message.chat.id, "📢 أرسل معرف القناة (مثال: @channel_name) لإضافتها كاشتراك إجباري:")
                bot.register_next_step_handler(msg, admin_add_channel_step)

            elif call.data == "admin_del_channel":
                settings = load_bot_settings()
                current = settings.get('force_channel', '')
                if current:
                    mk = types.InlineKeyboardMarkup(row_width=2)
                    mk.add(
                        types.InlineKeyboardButton("🗑️ نعم، احذفها", callback_data="admin_confirm_del_channel"),
                        types.InlineKeyboardButton("❌ لا، إلغاء", callback_data="admin_cancel_del_channel")
                    )
                    bot.send_message(call.message.chat.id,
                        f"📢 القناة الحالية: `{current}`\n\nهل تريد حذف هذه القناة من الاشتراك الإجباري؟",
                        parse_mode="Markdown", reply_markup=mk)
                else:
                    bot.send_message(call.message.chat.id, "❌ لا توجد قناة اشتراك إجباري مضافة.")

            elif call.data == "admin_confirm_del_channel":
                settings = load_bot_settings()
                current = settings.get('force_channel', '')
                if current:
                    settings['force_channel'] = ''
                    save_bot_settings(settings)
                    try:
                        bot.edit_message_text(f"✅ تم حذف قناة الاشتراك الإجباري: `{current}`",
                            call.message.chat.id, call.message.message_id, parse_mode="Markdown")
                    except:
                        bot.send_message(call.message.chat.id, f"✅ تم حذف قناة الاشتراك الإجباري: `{current}`", parse_mode="Markdown")
                else:
                    bot.send_message(call.message.chat.id, "❌ لا توجد قناة مضافة.")

            elif call.data == "admin_cancel_del_channel":
                try:
                    bot.edit_message_text("🚫 تم إلغاء الحذف.",
                        call.message.chat.id, call.message.message_id)
                except:
                    bot.send_message(call.message.chat.id, "🚫 تم إلغاء الحذف.")

            elif call.data == "admin_add_code":
                msg = bot.send_message(call.message.chat.id, "🎟️ أرسل اسم الكود:")
                bot.register_next_step_handler(msg, admin_code_name_step)

            elif call.data == "admin_list_codes":
                settings = load_bot_settings()
                codes = settings.get('codes', {})
                if not codes:
                    bot.send_message(call.message.chat.id, "❌ لا توجد أكواد مضافة.")
                else:
                    msg = "📋 **قائمة الأكواد:**\n\n"
                    for code, data in codes.items():
                        msg += f"🎟️ `{code}` — {data.get('uses', 0)} استخدام متبقي — {data.get('points', 0)} نقطة\n"
                    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")

            elif call.data == "admin_list_servers":
                users = load_users()
                if not users:
                    bot.send_message(call.message.chat.id, "❌ لا يوجد مستخدمون.")
                else:
                    msg = "🖥️ **قائمة السيرفرات والمستخدمين:**\n\n"
                    for uname, data in users.items():
                        status = "🔴 محظور" if data.get('banned') else "🟢 نشط"
                        password = data.get('password_plain', '🔒 مشفرة')
                        msg += (f"👤 `{uname}` {status}\n"
                                f"   🔑 كلمة المرور: `{password}`\n"
                                f"   💰 النقاط: `{data.get('points', 0)}`\n"
                                f"   🖥️ السيرفرات: `{data.get('max_servers', 1)}`\n\n")
                    for chunk in [msg[i:i+3500] for i in range(0, len(msg), 3500)]:
                        bot.send_message(call.message.chat.id, chunk, parse_mode="Markdown")

            elif call.data == "admin_add_points":
                msg = bot.send_message(call.message.chat.id, "💰 أرسل اسم المستخدم الذي تريد إضافة نقاط له:")
                bot.register_next_step_handler(msg, admin_add_points_user_step)

            elif call.data == "admin_del_points":
                msg = bot.send_message(call.message.chat.id, "➖ أرسل اسم المستخدم الذي تريد خصم نقاط منه:")
                bot.register_next_step_handler(msg, admin_del_points_user_step)

            elif call.data == "admin_check_user":
                msg = bot.send_message(call.message.chat.id, "🔍 أرسل اسم المستخدم لفحصه:")
                bot.register_next_step_handler(msg, admin_check_user_step)

            elif call.data == "admin_set_server_cost":
                settings = load_bot_settings()
                current_cost = settings.get('points_per_server', 10)
                msg = bot.send_message(call.message.chat.id,
                    f"⚙️ **تكلفة السيرفر الإضافي الحالية:** `{current_cost}` نقطة\n\nأرسل العدد الجديد من النقاط لكل سيرفر إضافي:",
                    parse_mode="Markdown")
                bot.register_next_step_handler(msg, admin_set_server_cost_step)

            elif call.data == "admin_set_panel_url":
                settings = load_bot_settings()
                current_url = settings.get('panel_url', 'غير محدد')
                msg = bot.send_message(call.message.chat.id,
                    f"🔗 **لينك اللوحة الحالي:** `{current_url}`\n\nأرسل لينك لوحة التحكم الجديد (مثال: https://mysite.replit.app):",
                    parse_mode="Markdown")
                bot.register_next_step_handler(msg, admin_set_panel_url_step)

        # --- خطوات الأدمن ---
        def admin_ban_user(message):
            uname = message.text.strip()
            users = load_users()
            if uname in users:
                users[uname]['banned'] = True
                save_users(users)
                bot.send_message(message.chat.id, f"✅ تم حظر `{uname}` من البوت بنجاح.", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")

        def admin_unban_user(message):
            uname = message.text.strip()
            users = load_users()
            if uname in users:
                users[uname]['banned'] = False
                save_users(users)
                bot.send_message(message.chat.id, f"✅ تم فك حظر `{uname}` بنجاح.", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")

        def admin_add_admin_step(message):
            try:
                new_id = int(message.text.strip())
                settings = load_bot_settings()
                admins = settings.get('admin_list', [])
                if new_id not in admins:
                    admins.append(new_id)
                    settings['admin_list'] = admins
                    save_bot_settings(settings)
                    bot.send_message(message.chat.id, f"✅ تم إضافة `{new_id}` كأدمن بنجاح.", parse_mode="Markdown")
                else:
                    bot.send_message(message.chat.id, "❌ هذا المستخدم أدمن بالفعل.")
            except ValueError:
                bot.send_message(message.chat.id, "❌ أرسل ID رقمي صحيح.")

        def admin_del_admin_step(message):
            try:
                del_id = int(message.text.strip())
                settings = load_bot_settings()
                admins = settings.get('admin_list', [])
                if del_id in admins:
                    admins.remove(del_id)
                    settings['admin_list'] = admins
                    save_bot_settings(settings)
                    bot.send_message(message.chat.id, f"✅ تم حذف `{del_id}` من الأدمنز.", parse_mode="Markdown")
                else:
                    bot.send_message(message.chat.id, "❌ هذا المستخدم ليس أدمن.")
            except ValueError:
                bot.send_message(message.chat.id, "❌ أرسل ID رقمي صحيح.")

        def admin_add_channel_step(message):
            channel = message.text.strip()
            if not channel.startswith('@'):
                channel = '@' + channel
            settings = load_bot_settings()
            settings['force_channel'] = channel
            save_bot_settings(settings)
            bot.send_message(message.chat.id, f"✅ تم إضافة قناة الاشتراك الإجباري: `{channel}`", parse_mode="Markdown")

        def admin_code_name_step(message):
            code_name = message.text.strip()
            msg = bot.send_message(message.chat.id, f"🎟️ الكود: `{code_name}`\n\nأرسل عدد الاستخدامات المسموحة:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: admin_code_uses_step(m, code_name))

        def admin_code_uses_step(message, code_name):
            try:
                uses = int(message.text.strip())
                msg = bot.send_message(message.chat.id, f"💰 أرسل عدد النقاط التي يحصل عليها المستخدم عند استخدام الكود:")
                bot.register_next_step_handler(msg, lambda m: admin_code_points_step(m, code_name, uses))
            except ValueError:
                bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

        def admin_code_points_step(message, code_name, uses):
            try:
                points = int(message.text.strip())
                settings = load_bot_settings()
                settings.setdefault('codes', {})[code_name] = {'uses': uses, 'points': points, 'used_by': []}
                save_bot_settings(settings)
                bot.send_message(message.chat.id,
                    f"✅ **تم إضافة الكود بنجاح!**\n\n"
                    f"🎟️ الكود: `{code_name}`\n"
                    f"🔢 الاستخدامات: `{uses}`\n"
                    f"💰 النقاط: `{points}`",
                    parse_mode="Markdown")
            except ValueError:
                bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

        def admin_del_points_user_step(message):
            uname = message.text.strip()
            users = load_users()
            if uname not in users:
                bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")
                return
            current_pts = users[uname].get('points', 0)
            msg = bot.send_message(message.chat.id,
                f"➖ رصيد `{uname}` الحالي: *{current_pts}* نقطة\n\nكم نقطة تريد خصمها؟",
                parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: admin_del_points_amount_step(m, uname))

        def admin_del_points_amount_step(message, uname):
            try:
                pts = int(message.text.strip())
                if pts <= 0:
                    bot.send_message(message.chat.id, "❌ أرسل رقماً أكبر من صفر.")
                    return
                users = load_users()
                old_pts = users[uname].get('points', 0)
                new_pts = max(0, old_pts - pts)
                users[uname]['points'] = new_pts
                save_users(users)
                bot.send_message(message.chat.id,
                    f"✅ تم خصم `{pts}` نقطة من `{uname}`.\n💰 كان رصيده: *{old_pts}* نقطة\n💰 رصيده الآن: *{new_pts}* نقطة",
                    parse_mode="Markdown")
                try:
                    tid = users[uname].get('telegram_id')
                    if tid:
                        bot.send_message(tid,
                            f"⚠️ تم خصم `{pts}` نقطة من حسابك من قِبل الأدمن.\n💰 رصيدك الحالي: *{new_pts}* نقطة",
                            parse_mode="Markdown")
                except: pass
            except ValueError:
                bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

        def admin_add_points_user_step(message):
            uname = message.text.strip()
            users = load_users()
            if uname not in users:
                bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")
                return
            msg = bot.send_message(message.chat.id, f"💰 كم نقطة تريد إضافتها لـ `{uname}`؟", parse_mode="Markdown")
            bot.register_next_step_handler(msg, lambda m: admin_add_points_amount_step(m, uname))

        def admin_add_points_amount_step(message, uname):
            try:
                pts = int(message.text.strip())
                users = load_users()
                users[uname]['points'] = users[uname].get('points', 0) + pts
                save_users(users)
                bot.send_message(message.chat.id, f"✅ تم إضافة `{pts}` نقطة لـ `{uname}`.\nرصيده الآن: `{users[uname]['points']}` نقطة.", parse_mode="Markdown")
                try:
                    tid = users[uname].get('telegram_id')
                    if tid:
                        bot.send_message(tid, f"🎉 تم إضافة `{pts}` نقطة لحسابك من الأدمن!\nرصيدك الآن: `{users[uname]['points']}` نقطة.", parse_mode="Markdown")
                except: pass
            except ValueError:
                bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

        def admin_check_user_step(message):
            uname = message.text.strip()
            users = load_users()
            if uname not in users:
                bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")
                return
            data = users[uname]
            status = "🔴 محظور" if data.get('banned') else "🟢 نشط"
            password = data.get('password_plain', '🔒 مشفرة')
            msg = (f"🔍 **معلومات المستخدم:**\n\n"
                   f"👤 الاسم: `{uname}`\n"
                   f"🔑 كلمة المرور: `{password}`\n"
                   f"📊 الحالة: {status}\n"
                   f"💰 النقاط: `{data.get('points', 0)}`\n"
                   f"🖥️ السيرفرات المسموحة: `{data.get('max_servers', 1)}`\n"
                   f"📅 تاريخ الإنشاء: `{str(data.get('created', '-'))[:10]}`\n"
                   f"📱 Telegram ID: `{data.get('telegram_id', '-')}`")
            bot.send_message(message.chat.id, msg, parse_mode="Markdown")

        def admin_set_server_cost_step(message):
            try:
                cost = int(message.text.strip())
                if cost < 0:
                    bot.send_message(message.chat.id, "❌ يجب أن يكون الرقم أكبر من أو يساوي صفر.")
                    return
                settings = load_bot_settings()
                settings['points_per_server'] = cost
                save_bot_settings(settings)
                bot.send_message(message.chat.id,
                    f"✅ تم تحديث تكلفة السيرفر الإضافي إلى `{cost}` نقطة بنجاح!",
                    parse_mode="Markdown")
            except ValueError:
                bot.send_message(message.chat.id, "❌ أرسل رقماً صحيحاً.")

        def admin_set_panel_url_step(message):
            url = message.text.strip()
            if not url.startswith('http'):
                bot.send_message(message.chat.id, "❌ اللينك يجب أن يبدأ بـ http أو https.")
                return
            settings = load_bot_settings()
            settings['panel_url'] = url
            save_bot_settings(settings)
            bot.send_message(message.chat.id,
                f"✅ تم تعيين لينك اللوحة بنجاح!\n\n🔗 `{url}`\n\nسيتم إرسال هذا اللينك للمستخدمين بعد إنشاء حساباتهم.",
                parse_mode="Markdown")

        print(" * Starting Advanced Telegram Bot...")
        bot.remove_webhook()
        bot.polling(none_stop=True)
    except Exception as e:
        print(f" * Telegram Bot Error: {e}")

if __name__ == '__main__':
    print(r"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   <i class="fas fa-fire"></i>  VEX  VPS <i class="fas fa-fire"></i>                                                ║
║   # 𝚅𝙿𝚂 𝙾𝙼𝙰𝚁                                              ║
║                                                                  ║
║   Master  : {mu:<48} ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""".format(mu=MASTER_USERNAME))

    # شغّل بوت التليجرام في ثريد منفصل
    threading.Thread(target=run_telegram_bot, daemon=True).start()

    # شغّل بورتات إضافية إن وُجدت
    start_configured_extra_ports()

    port = int(os.environ.get("PORT", 9795))
    panel_url_env = os.environ.get("PANEL_URL", "").strip()
    if panel_url_env:
        # حفظ رابط اللوحة تلقائياً من متغير البيئة إن وُجد
        cfg = load_owner_config()
        if not cfg.get('panel_url'):
            cfg['panel_url'] = panel_url_env
            save_owner_config(cfg)
    print(f"🌐 Panel running on port {port}")
    if panel_url_env:
        print(f"   URL: {panel_url_env}")
    print(f"   Login: {MASTER_USERNAME}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
