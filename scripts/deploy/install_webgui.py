#!/usr/bin/env python3
"""Prepare a pinned WebGUI release for the current VENTUNO user.

Default: install files and reload the user manager without starting/stopping a
service. --start explicitly enables/starts the owned unit and switches an active
owned service to the selected release. No sudo, login changes, browser launch,
ROS operation, Tailscale configuration, or existing checkout modification.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import subprocess
import sys
from urllib.parse import urlsplit

NVME = Path('/srv/vision-data')
RELEASES = NVME / 'releases/vision-webgui'
TOOLS = NVME / 'tools/vision-webgui'
VENV = TOOLS / 'venv'
STATE = NVME / 'state/vision-webgui'
IDENTITY = STATE / 'identity'
ACCOUNTS = IDENTITY / 'accounts.json'
INITIAL_PASSWORD = IDENTITY / 'initial-login.txt'
LIBRARY = NVME / 'data/ecu-library'
BROWSER = STATE / 'browser'
NATIVE_FIREFOX = TOOLS / 'firefox/firefox'
RUN = NVME / 'run/vision-webgui'
BACKUPS = STATE / 'deployment-backups'
ENVIRONMENT_RECORD = TOOLS / 'environment.json'
UNIT_NAME = 'vision-webgui.service'
DESKTOP_NAME = 'vision-webgui.desktop'
MANAGED = '# Managed by Vision WebGUI installer v1\n'
STATION_MARKER = b'<meta name="vision-deployment" content="station">'
STATIC_ASSET = re.compile(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*\.(?:js|css|woff2?|ttf|svg|png|ico)\Z')
RELEASE_PATH = re.compile(r'/srv/vision-data/releases/vision-webgui/[0-9a-f]{40}\Z')


class InstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class Plan:
    release: Path
    origin: str | None
    browser: Path
    uid: int
    username: str
    home: Path
    unit: Path
    launcher: Path
    autostart: Path
    bus_environment: dict
    environment: dict
    was_active: bool
    requirements_hash: str
    server_version: str
    install_dependencies: bool


def _run(arguments, *, label, env=None, cwd=None, accepted=(0,)):
    result = subprocess.run(arguments, env=env, cwd=cwd, capture_output=True, text=True,
                            timeout=300 if label == 'install dependencies' else 60)
    if result.returncode not in accepted:
        raise InstallError(f'{label} failed (exit {result.returncode}); no elevation was attempted')
    return result


def _no_symlinks(path):
    path = Path(path)
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise InstallError('absolute paths without symlink components are required')
    return path


def _read_regular(path, limit=65536, *, owner=None):
    _no_symlinks(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > limit
                or (owner is not None and info.st_uid != owner)):
            raise InstallError('invalid deployment file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            body = stream.read(limit + 1)
        if len(body) > limit:
            raise InstallError('deployment file exceeds its bound')
        return body
    finally:
        os.close(fd)


def validate_origin(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 200 or re.search(r'[\s%$"\\]', value):
        raise InstallError('HTTPS origin must be a single canonical origin')
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if (parsed.scheme != 'https' or parsed.path or parsed.query or parsed.fragment
                or parsed.username is not None or parsed.password is not None
                or not host or host != host.lower()
                or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                       for label in host.split('.'))
                or (port is not None and not 1 <= port <= 65535)
                or value != 'https://' + host + (f':{port}' if port is not None else '')):
            raise InstallError('HTTPS origin must contain only a lower-case host and optional port')
    except ValueError:
        raise InstallError('invalid HTTPS origin') from None
    return value


def validate_browser(value, uid):
    if value not in ('/usr/bin/firefox', str(NATIVE_FIREFOX)):
        raise InstallError('browser must be native /usr/bin/firefox or the managed NVMe Firefox executable')
    browser = _no_symlinks(Path(value))
    fd = os.open(browser, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        expected_owner = uid if browser == NATIVE_FIREFOX else 0
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != expected_owner
                or info.st_mode & 0o022 or not os.access(browser, os.X_OK)):
            raise InstallError('native Firefox must have the expected owner and safe executable permissions')
        header = os.read(fd, 64)
        if not header.startswith(b'\x7fELF'):
            raise InstallError('Firefox Snap/launcher wrappers are unsupported for the NVMe profile; supply native Mozilla Firefox with --browser')
    finally:
        os.close(fd)
    return browser


def validate_static(release, uid):
    dist = _no_symlinks(release / 'webgui/dist')
    index = _read_regular(dist / 'index.html', 4 * 1024 * 1024, owner=uid)
    if index.count(STATION_MARKER) != 1:
        raise InstallError('build WebGUI with VITE_VISION_DEPLOYMENT=station before installation')
    total = len(index) + len(_read_regular(dist / 'THIRD_PARTY_NOTICES.txt', 4 * 1024 * 1024, owner=uid))
    assets = _no_symlinks(dist / 'assets')
    if not assets.is_dir():
        raise InstallError('built assets directory is missing')
    count = 0
    suffixes = set()
    for path in assets.iterdir():
        count += 1
        if count > 126 or not STATIC_ASSET.fullmatch(path.name):
            raise InstallError('invalid or excessive static assets')
        total += len(_read_regular(path, 4 * 1024 * 1024, owner=uid))
        suffixes.add(path.suffix)
        if total > 24 * 1024 * 1024:
            raise InstallError('static build exceeds the station limit')
    if not {'.js', '.css'} <= suffixes:
        raise InstallError('complete station JavaScript and CSS assets are required')


def _existing_managed(path, uid):
    _no_symlinks(path)
    if not path.exists():
        return None
    body = _read_regular(path, owner=uid)
    if not body.startswith(MANAGED.encode('ascii')):
        raise InstallError(f'refusing to replace an unmanaged file: {path.name}')
    return body


def _environment(home):
    environment = os.environ.copy()
    environment.update({'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
                        'TMPDIR': str(RUN), 'PIP_NO_CACHE_DIR': '1',
                        'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PIP_CONFIG_FILE': '/dev/null',
                        'HOME': str(home)})
    # Do not inherit an index URL containing workstation credentials.
    for name in ('PIP_INDEX_URL', 'PIP_EXTRA_INDEX_URL', 'PIP_TARGET', 'PIP_PREFIX',
                 'PYTHONHOME', 'PYTHONPATH'):
        environment.pop(name, None)
    return environment


def validate_plan(release_value, origin_value, browser_value='/usr/bin/firefox'):
    if not isinstance(release_value, str) or not RELEASE_PATH.fullmatch(release_value):
        raise InstallError('release must be /srv/vision-data/releases/vision-webgui/<full 40-character SHA>')
    release = _no_symlinks(Path(release_value))
    origin = validate_origin(origin_value)
    uid = os.getuid()
    if uid == 0 or os.geteuid() != uid:
        raise InstallError('run as the existing desktop user without sudo or privilege switching')
    account = pwd.getpwuid(uid)
    browser = validate_browser(browser_value, uid)
    home = _no_symlinks(Path(account.pw_dir))
    if (not home.is_dir() or home.stat().st_uid != uid
            or any(c in str(home) for c in '\r\n%$"\\')):
        raise InstallError('invalid current-user home directory')
    _no_symlinks(NVME)
    if not os.path.ismount(NVME):
        raise InstallError('/srv/vision-data must be mounted; there is no eMMC fallback')
    for executable in ('/usr/bin/git', '/usr/bin/systemctl', '/usr/bin/mountpoint'):
        if not os.access(executable, os.X_OK):
            raise InstallError(f'required executable is unavailable: {Path(executable).name}')
    if not release.is_dir() or release.stat().st_uid != uid:
        raise InstallError('the pinned release must belong to the current user')
    environment = _environment(home)
    git = ['/usr/bin/git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', str(release)]
    head = _run([*git, 'rev-parse', '--verify', 'HEAD^{commit}'], label='verify release HEAD').stdout.strip()
    top = _run([*git, 'rev-parse', '--show-toplevel'], label='verify release root').stdout.strip()
    if head != release.name or top != str(release):
        raise InstallError('release directory, Git root and exact HEAD must agree')
    _run([*git, 'diff', '--quiet', '--no-ext-diff', 'HEAD', '--'], label='verify clean tracked release')
    if _run([*git, 'ls-files', '--others', '--exclude-standard'], label='verify release extras').stdout.strip():
        raise InstallError('untracked release files are not allowed outside ignored build output')
    for name in ('requirements-station.txt', 'src/vision_api/station.py', 'src/vision_api/identity.py',
                 'config/ecu_profiles/etc3_poc_v1.json', 'docs/templates/ECU_REFERENCE_PROFILE_V1_TEMPLATE.json'):
        _read_regular(release / name, 512 * 1024, owner=uid)
        _run([*git, 'ls-files', '--error-unmatch', '--', name], label='verify tracked station input')
    requirements = _read_regular(release / 'requirements-station.txt', owner=uid)
    requirements_hash = hashlib.sha256(requirements).hexdigest()
    server_pin = re.search(rb'^waitress==([0-9]+\.[0-9]+\.[0-9]+) --hash=sha256:[0-9a-f]{64}$', requirements, re.MULTILINE)
    if server_pin is None:
        raise InstallError('an exact hashed Waitress release is required')
    server_version = server_pin.group(1).decode('ascii')
    validate_static(release, uid)
    for path in (TOOLS, VENV, STATE, IDENTITY, LIBRARY, BROWSER, RUN, BACKUPS):
        _no_symlinks(path)
        if path.exists() and (not path.is_dir() or path.stat().st_uid != uid):
            raise InstallError('application directories must belong to the current user')
    unit = home / '.config/systemd/user' / UNIT_NAME
    launcher = home / '.local/share/applications' / DESKTOP_NAME
    autostart = home / '.config/autostart' / DESKTOP_NAME
    for path in (unit, launcher, autostart):
        _existing_managed(path, uid)
    bus_environment = environment.copy()
    runtime = Path('/run/user') / str(uid)
    if not runtime.is_dir() or runtime.stat().st_uid != uid or not (runtime / 'bus').exists():
        raise InstallError('the existing user bus must be available; login/linger settings are not changed')
    bus_environment.update({'XDG_RUNTIME_DIR': str(runtime),
                            'DBUS_SESSION_BUS_ADDRESS': f'unix:path={runtime}/bus'})
    _run(['/usr/bin/systemctl', '--user', 'show', '--property=Version', '--value'],
         label='check existing user manager', env=bus_environment)
    fragment = _run(['/usr/bin/systemctl', '--user', 'show', '--property=FragmentPath', '--value', UNIT_NAME],
                    label='inspect existing unit', env=bus_environment, accepted=(0, 1)).stdout.strip()
    if fragment and fragment != str(unit):
        raise InstallError('a same-name unit exists outside the managed user-unit path')
    was_active = _run(['/usr/bin/systemctl', '--user', 'is-active', '--quiet', UNIT_NAME],
                      label='inspect service state', env=bus_environment, accepted=(0, 3, 4)).returncode == 0
    if was_active and _existing_managed(unit, uid) is None:
        raise InstallError('an active unit without its managed file cannot be replaced')
    install_dependencies = True
    if ENVIRONMENT_RECORD.exists():
        record = json.loads(_read_regular(ENVIRONMENT_RECORD, owner=uid))
        if type(record) is not dict or set(record) != {'schema', 'requirements_sha256'} or record['schema'] != 'vision.webgui.environment.v1':
            raise InstallError('invalid managed environment record')
        install_dependencies = record['requirements_sha256'] != requirements_hash
    elif VENV.exists():
        raise InstallError('an unmarked existing virtual environment cannot be modified')
    if VENV.exists():
        config = _read_regular(VENV / 'pyvenv.cfg', owner=uid)
        if b'include-system-site-packages = true' not in config or not (VENV / 'bin/python').is_file():
            raise InstallError('the managed virtual environment is incomplete')
    else:
        install_dependencies = True
    if install_dependencies and was_active:
        raise InstallError('stop the owned WebGUI service explicitly before replacing its shared dependencies')
    return Plan(release, origin, browser, uid, account.pw_name, home, unit, launcher, autostart,
                bus_environment, environment, was_active, requirements_hash, server_version, install_dependencies)


def _mkdir(path, *, private=False):
    _no_symlinks(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    _no_symlinks(path)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise InstallError('directory ownership mismatch')
    if private:
        path.chmod(0o700)


def _write(path, body, mode=0o600):
    _no_symlinks(path)
    temporary = path.with_name('.' + path.name + '-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _unit(plan):
    command = [str(VENV / 'bin/python'), '-B', '-m', 'vision_api.station', '--port', '18490',
               '--accounts', str(ACCOUNTS), '--library-root', str(LIBRARY),
               '--dist', str(plan.release / 'webgui/dist')]
    if plan.origin:
        command.extend(('--https-origin', plan.origin))
    return (MANAGED + f'# Release: {plan.release}\n' + f'''[Unit]
Description=Vision WebGUI reader ({plan.release.name[:12]})

[Service]
Type=simple
WorkingDirectory={plan.release}
Environment="HOME={plan.home}"
Environment="PYTHONPATH={plan.release}/src"
Environment="PYTHONNOUSERSITE=1"
Environment="PYTHONDONTWRITEBYTECODE=1"
Environment="TMPDIR={RUN}"
ExecStartPre=/usr/bin/mountpoint --quiet {NVME}
ExecStart={' '.join(command)}
UMask=0077
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
TasksMax=32
MemoryMax=512M
TimeoutStopSec=15s

[Install]
WantedBy=default.target
''').encode('utf-8')


def _desktop(plan):
    return (MANAGED + f'''[Desktop Entry]
Type=Application
Name=Vision WebGUI
Comment=Vision reader desktop
Exec={plan.browser} --no-remote --profile {BROWSER} --kiosk http://127.0.0.1:18490/
TryExec={plan.browser}
Terminal=false
Icon=applications-system
Categories=Utility;
X-GNOME-Autostart-enabled=true
''').encode('utf-8')


def install(plan, *, start=False):
    os.umask(0o077)
    for path in (TOOLS, STATE, IDENTITY, LIBRARY, BROWSER, RUN, BACKUPS):
        _mkdir(path, private=True)
    environment = dict(plan.environment, PYTHONPATH=str(plan.release / 'src'))
    if not VENV.exists():
        _run([sys.executable, '-B', '-m', 'venv', '--system-site-packages', '--copies', str(VENV)],
             label='create virtual environment', env=environment)
    python = str(VENV / 'bin/python')
    if plan.install_dependencies:
        # An interrupted pip download remains retryable as an owned environment.
        _write(ENVIRONMENT_RECORD, (json.dumps({'schema': 'vision.webgui.environment.v1',
                'requirements_sha256': None}) + '\n').encode('ascii'))
        _run([python, '-B', '-m', 'pip', 'install', '--require-hashes', '--only-binary=:all:',
              '--ignore-installed', '--no-cache-dir', '-r', str(plan.release / 'requirements-station.txt')],
             label='install dependencies', env=environment)
        _write(ENVIRONMENT_RECORD, (json.dumps({'schema': 'vision.webgui.environment.v1',
                'requirements_sha256': plan.requirements_hash}) + '\n').encode('ascii'))
    _run([python, '-B', '-c',
          'import sys, pathlib, importlib.metadata, waitress; '
          'valid = (importlib.metadata.version("waitress") == sys.argv[1] and '
          'pathlib.Path(waitress.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())); '
          'sys.exit(0 if valid else 1)',
          plan.server_version], label='verify pinned server in managed environment', env=environment)
    if not ACCOUNTS.exists():
        _run([python, '-B', '-m', 'vision_api.identity', '--accounts', str(ACCOUNTS),
              '--forbid-root', str(plan.release / 'webgui/dist'), 'provision', 'operator',
              '--generate-to', str(INITIAL_PASSWORD)], label='provision initial reader', env=environment)
    _run([python, '-B', '-c',
          'import sys; from vision_api.identity import IdentityStore; from vision_api.station import _load_static; '
          'IdentityStore(sys.argv[1], forbidden_roots=(sys.argv[2],)); _load_static(sys.argv[2])',
          str(ACCOUNTS), str(plan.release / 'webgui/dist')],
         label='validate account store and station build', env=environment)
    replacements = ((plan.unit, _unit(plan)), (plan.launcher, _desktop(plan)), (plan.autostart, _desktop(plan)))
    changes = [(path, body, _existing_managed(path, plan.uid)) for path, body in replacements]
    changes = [(path, body, old) for path, body, old in changes if body != old]
    previous = [(path, old) for path, _, old in changes if old is not None]
    if previous:
        backup = BACKUPS / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4))
        _mkdir(backup, private=True)
        manifest = {'schema': 'vision.webgui.backup.v1', 'next_release': str(plan.release), 'files': []}
        for index, (path, old) in enumerate(previous):
            name = f'{index}-{path.name}'
            _write(backup / name, old)
            manifest['files'].append({'target': str(path), 'backup': name})
        _write(backup / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
        print(f'Previous managed deployment files saved: {backup}')
    for path, body, _ in changes:
        _mkdir(path.parent)
        _write(path, body)
    _run(['/usr/bin/systemctl', '--user', 'daemon-reload'], label='reload user manager', env=plan.bus_environment)
    if start:
        _run(['/usr/bin/systemctl', '--user', 'enable', '--now', UNIT_NAME],
             label='enable and start owned WebGUI', env=plan.bus_environment)
        if plan.was_active:
            _run(['/usr/bin/systemctl', '--user', 'restart', UNIT_NAME],
                 label='switch active owned WebGUI release', env=plan.bus_environment)
        _run(['/usr/bin/systemctl', '--user', 'is-active', '--quiet', UNIT_NAME],
             label='verify owned WebGUI is active', env=plan.bus_environment)
    print('WebGUI started.' if start else 'WebGUI prepared. Service start/stop state was not changed.')
    print(f'Pinned release: {plan.release.name}')
    print('Local URL: http://127.0.0.1:18490/')
    print(f'Reader: operator; initial password file: {INITIAL_PASSWORD} (existing accounts are preserved).')
    print('Core: NOT_CONNECTED; active specimen session: none.')
    if plan.origin:
        print(f'Configured private HTTPS origin: {plan.origin}')
        print('Tailscale Serve was not changed. Review its existing routes and permissions before running:')
        https_port = urlsplit(plan.origin).port or 443
        print(f'  tailscale serve --bg --https={https_port} http://127.0.0.1:18490')
    print('Firefox launcher/autostart files are prepared; no desktop window was opened.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True)
    parser.add_argument('--https-origin')
    parser.add_argument('--browser', default='/usr/bin/firefox', help='Native Firefox executable; Snap wrappers are rejected.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--start', action='store_true')
    mode.add_argument('--validate-only', action='store_true', help='Read-only preflight; create or change nothing.')
    args = parser.parse_args(argv)
    try:
        plan = validate_plan(args.release, args.https_origin, args.browser)
        if args.validate_only:
            print(f'Validated pinned station release {plan.release.name}; no changes made.')
            return 0
        install(plan, start=args.start)
        return 0
    except (InstallError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f'WebGUI installation stopped: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
