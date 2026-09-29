#!/usr/bin/env python3
"""Cooperating local-process run locks. Never use age as owner-death evidence."""
import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time
import uuid


class LockError(Exception):
    pass


def canonical_repo(value):
    path = Path(value).resolve()
    if path.exists():
        result = subprocess.run(['git', '-C', str(path), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if result.returncode == 0:
            path = Path(result.stdout.strip()).resolve()
    return str(path)


def key_for(repo):
    return hashlib.sha256(repo.encode()).hexdigest()


def boot_identity():
    if sys.platform.startswith('linux'):
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if sys.platform == 'darwin':
        return subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'], text=True).strip()
    raise LockError('owner process probing is unsupported on this platform')


def process_start(pid):
    """Native birth identity avoids treating a reused PID as the previous owner."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    if sys.platform.startswith('linux'):
        # comm may contain spaces or parentheses; fields after its final ')' are stable.
        try:
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        except FileNotFoundError:
            return None
        return None if fields[0] in ('Z', 'X') else fields[19]
    if sys.platform == 'darwin':
        process_state = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
        if process_state.returncode == 0 and process_state.stdout.strip().startswith('Z'):
            return None
        class BSDInfo(ctypes.Structure):
            _fields_ = [
                ('flags', ctypes.c_uint32), ('status', ctypes.c_uint32),
                ('xstatus', ctypes.c_uint32), ('pid', ctypes.c_uint32),
                ('ppid', ctypes.c_uint32), ('uid', ctypes.c_uint32),
                ('gid', ctypes.c_uint32), ('ruid', ctypes.c_uint32),
                ('rgid', ctypes.c_uint32), ('svuid', ctypes.c_uint32),
                ('svgid', ctypes.c_uint32), ('reserved', ctypes.c_uint32),
                ('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32),
                ('nfiles', ctypes.c_uint32), ('pgid', ctypes.c_uint32),
                ('pjobc', ctypes.c_uint32), ('tdev', ctypes.c_uint32),
                ('tpgid', ctypes.c_uint32), ('nice', ctypes.c_int32),
                ('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64),
            ]
        lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        lib.proc_pidinfo.restype = ctypes.c_int
        info = BSDInfo()
        size = lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        if size != ctypes.sizeof(info) or info.pid != pid:
            raise LockError('process birth identity unavailable')
        return None if info.status == 5 else f'{info.start_sec}:{info.start_usec}'
    raise LockError('owner process probing is unsupported on this platform')


def bind_owner(pid):
    if pid is None:
        return {'kind': 'unknown'}
    if pid <= 1:
        raise LockError('owner PID must identify an explicitly chosen durable process')
    start = process_start(pid)
    if start is None:
        raise LockError('owner PID is not running')
    return {'kind': 'pid', 'pid': pid, 'host': socket.gethostname(), 'boot_id': boot_identity(), 'process_start': start, 'platform': sys.platform}


def owner_status(data):
    if data.get('legacy'):
        return 'ownerless/legacy'
    owner = data['owner']
    if owner['kind'] == 'unknown':
        return 'unknown-owner'
    try:
        if owner['host'] != socket.gethostname() or owner['platform'] != sys.platform or owner['boot_id'] != boot_identity():
            return 'unknown-owner'
        birth = process_start(owner['pid'])
        return 'owned/active' if birth == owner['process_start'] else 'dead-owner'
    except (OSError, LockError, subprocess.SubprocessError, ValueError, IndexError):
        return 'unknown-owner'


def parse_metadata(raw, key):
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise LockError('duplicate metadata field')
            result[name] = value
        return result
    try:
        text = raw.decode('utf-8')
        if text.lstrip().startswith('{'):
            data = json.loads(text, object_pairs_hook=pairs)
            if data.get('version') != 2:
                raise LockError('unsupported lock version')
            required = ('project', 'repo_path', 'run_id', 'branch', 'start_head', 'created_at')
            if any(not isinstance(data.get(k), str) for k in required):
                raise LockError('missing or invalid lock fields')
            if not data['project'] or not re.fullmatch(r'[a-f0-9]{32}', data['run_id']):
                raise LockError('invalid project or run_id')
            owner = data.get('owner')
            if not isinstance(owner, dict) or owner.get('kind') not in ('unknown', 'pid'):
                raise LockError('invalid owner metadata')
            if owner['kind'] == 'pid':
                if type(owner.get('pid')) is not int or owner['pid'] <= 1:
                    raise LockError('invalid owner PID')
                if any(not isinstance(owner.get(k), str) or not owner[k] for k in ('host', 'boot_id', 'process_start')):
                    raise LockError('incomplete owner identity')
                pattern = {'linux': r'[0-9]+', 'darwin': r'[0-9]+:[0-9]+'}.get(owner.get('platform'))
                if pattern is None or not re.fullmatch(pattern, owner['process_start']):
                    raise LockError('invalid native process birth identity')
            elif set(owner) != {'kind'}:
                raise LockError('ambiguous unknown owner metadata')
            if 'legacy' in data:
                raise LockError('ambiguous legacy marker')
        else:
            lines = text.splitlines()
            if not lines or any('=' not in line for line in lines):
                raise LockError('malformed legacy lock')
            data = pairs(line.split('=', 1) for line in lines)
            if not data.get('project') or not data.get('repo'):
                raise LockError('legacy project/repo missing')
            if any(k not in {'project', 'repo', 'cwd', 'branch', 'head', 'created_at', 'created_epoch'} for k in data):
                raise LockError('unrecognized legacy metadata; recovery refused')
            data['repo_path'] = data['repo']
            data['legacy'] = True
        repo = data['repo_path']
        if not os.path.isabs(repo) or key_for(repo) != key:
            raise LockError('recorded repository does not match lock key')
        return data
    except (UnicodeError, ValueError, TypeError, AttributeError) as exc:
        raise LockError(f'malformed metadata: {exc}') from exc


def read_snapshot(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise LockError('lock target must be a regular file')
        raw = source.read(1024 * 1024 + 1)
        after = os.fstat(source.fileno())
    if len(raw) > 1024 * 1024 or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise LockError('oversized or changing lock snapshot')
    return raw, hashlib.sha256(raw).hexdigest(), (before.st_dev, before.st_ino)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_write(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


@contextmanager
def guard(root, key):
    root.mkdir(parents=True, exist_ok=True)
    guards = root / '.guards'
    guards.mkdir(exist_ok=True)
    # Guard inodes live forever: removing one splits queued writers into two domains.
    fd = os.open(guards / key, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise LockError('invalid serialization guard')
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def describe(path, max_age):
    snapshot = read_snapshot(path)
    if snapshot is None:
        return {'status': 'unlocked', 'lock': str(path), 'key': path.stem}
    raw, digest, _ = snapshot
    result = {'status': 'locked', 'lock': str(path), 'key': path.stem, 'digest': digest}
    try:
        data = parse_metadata(raw, path.stem)
        result.update(metadata=data, owner_status=owner_status(data))
        epoch = data.get('created_epoch')
        valid_epoch = (type(epoch) is int and epoch >= 0) or (isinstance(epoch, str) and epoch.isdigit())
        result['stale'] = time.time() - int(epoch) > max_age if valid_epoch else None
        result['orphaned'] = not Path(data['repo_path']).exists()
    except LockError as exc:
        result.update(owner_status='unknown-owner', stale=None, orphaned=None, error=str(exc))
    return result


def validate(path, project, repo, run_id, expected=None):
    if not run_id:
        raise LockError('caller --run-id required; use --no-lock only for an explicitly unlocked finish')
    snapshot = read_snapshot(path)
    if snapshot is None:
        raise LockError('no lock for this worktree')
    data = parse_metadata(snapshot[0], path.stem)
    if data.get('legacy') or data.get('run_id') != run_id or data['project'] != project or data['repo_path'] != repo:
        raise LockError('project, canonical repo and caller run_id must match the lock owner')
    if expected is not None and snapshot[1] != expected:
        raise LockError('lock snapshot changed; current lock retained')
    return snapshot


def archive_remove(path, snapshot, action, reason, recovery_check=None):
    archive = path.parent / '.archive'
    archive.mkdir(exist_ok=True)
    event = archive / uuid.uuid4().hex
    event.mkdir(mode=0o700)
    raw, digest, inode = snapshot
    record = {'action': action, 'reason': reason, 'lock': str(path), 'key': path.stem,
              'digest': digest, 'at': datetime.now(timezone.utc).isoformat(), 'state': 'prepared'}
    # Bytes and prepared audit must be durable before releasing exclusivity.
    durable_write(event / 'original.lock', raw)
    durable_write(event / 'prepared.json', json_bytes(record))
    sync_dir(event)
    sync_dir(archive)
    sync_dir(path.parent)
    current = read_snapshot(path)
    if current is None or current[1:] != (digest, inode):
        raise LockError('lock snapshot changed before removal; prepared archive retained')
    if recovery_check is not None:
        recovery_check(parse_metadata(current[0], path.stem))
    os.rename(path, event / 'removed.lock')
    sync_dir(event)
    sync_dir(path.parent)
    record['state'] = 'completed'
    durable_write(event / 'completed.json', json_bytes(record))
    sync_dir(event)
    return str(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock-dir', required=True)
    parser.add_argument('--max-age', type=int, default=43200)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('acquire', 'validate', 'release', 'status', 'recover', 'repo'):
        command = sub.add_parser(name)
        target = command.add_mutually_exclusive_group()
        target.add_argument('--repo', default=None)
        if name in ('status', 'recover'):
            target.add_argument('--key')
        if name == 'status':
            target.add_argument('--all', action='store_true')
        if name in ('acquire', 'validate', 'release'):
            command.add_argument('--project', required=True)
        if name in ('validate', 'release'):
            command.add_argument('--run-id', required=True)
        if name == 'acquire':
            command.add_argument('--owner-pid', type=int)
        if name in ('release', 'recover'):
            command.add_argument('--digest', required=name == 'release')
        if name == 'recover':
            command.add_argument('--reason')
            command.add_argument('--acknowledge-legacy', action='store_true')
            command.add_argument('--acknowledge-unknown', action='store_true')
    args = parser.parse_args()
    root = Path(args.lock_dir).resolve()
    repo = canonical_repo(args.repo or os.getcwd())
    if args.command == 'repo':
        print(repo)
        return 0
    key = getattr(args, 'key', None) or key_for(repo)
    if not re.fullmatch('[a-f0-9]{64}', key):
        raise LockError('key must be the full canonical worktree SHA-256')
    path = root / f'{key}.lock'
    if args.command == 'status':
        if args.all:
            print(json.dumps([describe(p, args.max_age) for p in sorted(root.glob('*.lock'))], indent=2))
            return 0
        state = describe(path, args.max_age)
        print(json.dumps(state, indent=2))
        return int(state['status'] == 'locked')
    if args.command == 'recover' and args.digest is None:
        if args.reason or args.acknowledge_legacy or args.acknowledge_unknown:
            raise LockError('recovery requires an exact --digest; omit mutation options for preview')
        print(json.dumps(describe(path, args.max_age), indent=2))
        return 0
    with guard(root, key):
        if args.command == 'acquire':
            if os.path.lexists(path):
                raise LockError('worktree is locked; inspect with scripts/agent_lock_status.sh --repo and use exact-owner finish or scripts/agent_lock_recover.sh')
            now = time.time()
            def git_value(*values):
                result = subprocess.run(['git', '-C', repo, *values], capture_output=True, text=True)
                return result.stdout.strip() if result.returncode == 0 else ''
            data = {'version': 2, 'run_id': uuid.uuid4().hex, 'project': args.project,
                    'repo_path': repo, 'branch': git_value('branch', '--show-current'),
                    'start_head': git_value('rev-parse', 'HEAD'), 'created_epoch': int(now),
                    'created_at': datetime.fromtimestamp(now, timezone.utc).isoformat(), 'owner': bind_owner(args.owner_pid)}
            if not args.project:
                raise LockError('project must not be empty')
            # Publish complete durable bytes with link's no-replacement guarantee.
            staging = root / '.pending'
            staging.mkdir(exist_ok=True)
            pending = staging / data['run_id']
            raw = json_bytes(data)
            durable_write(pending, raw)
            os.link(pending, path)
            sync_dir(root)
            print(json.dumps({'run_id': data['run_id'], 'digest': hashlib.sha256(raw).hexdigest(), 'repo': repo}))
        elif args.command in ('validate', 'release'):
            snapshot = validate(path, args.project, repo, args.run_id, getattr(args, 'digest', None))
            if args.command == 'validate':
                print(snapshot[1])
            else:
                archive = archive_remove(path, snapshot, 'finish', 'exact caller run_id and snapshot')
                print(f'Run lock: released; archive: {archive}')
        else:
            if not args.reason or not args.reason.strip():
                raise LockError('explicit nonempty --reason required')
            if not re.fullmatch('[a-f0-9]{64}', args.digest):
                raise LockError('exact full snapshot --digest required')
            snapshot = read_snapshot(path)
            if snapshot is None or snapshot[1] != args.digest:
                raise LockError('lock snapshot changed or absent; recovery refused')
            def check_recovery(data):
                state = owner_status(data)
                if state == 'owned/active':
                    raise LockError('active owner; recovery refused regardless of age or missing repo')
                if state == 'ownerless/legacy' and not args.acknowledge_legacy:
                    raise LockError('legacy owner cannot be proven dead; --acknowledge-legacy required')
                if state == 'unknown-owner' and not args.acknowledge_unknown:
                    raise LockError('unknown owner cannot be proven dead; --acknowledge-unknown required')
            check_recovery(parse_metadata(snapshot[0], key))
            archive = archive_remove(path, snapshot, 'recovery', args.reason, check_recovery)
            print(json.dumps({'status': 'recovered', 'digest': args.digest, 'archive': archive}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (LockError, OSError, subprocess.SubprocessError) as exc:
        print(f'Run lock error: {exc}', file=sys.stderr)
        sys.exit(2)
