"""Lock lifecycle contract, using isolated files and real wrapper processes only."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def hub(tmp_path):
    scripts = tmp_path / 'hub' / 'scripts'
    scripts.mkdir(parents=True)
    for pattern in ('agent_*lock*', 'agent_start.sh', 'agent_finish.sh'):
        for source in (ROOT / 'scripts').glob(pattern):
            shutil.copy2(source, scripts / source.name)
    (scripts / 'db_common.sh').write_text('''ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHARED_ROOT="$ROOT_DIR"
PYTHON_BIN="$TEST_PYTHON"
run_agent_hub() {
  printf '%s\\n' "$*" >> "$ROOT_DIR/effects"
  if [[ "${FAIL_ACTION:-}" == "$1" ]]; then return 1; fi
  if [[ "$*" == *"--format json"* ]]; then echo '{}'; fi
  if [[ -n "${REPLACE_ON_ACTION:-}" && "$1" == "$REPLACE_ON_ACTION" ]]; then
    "$PYTHON_BIN" -c 'import json, pathlib, sys; p=next((pathlib.Path(sys.argv[1])/".local/run-locks").glob("*.lock")); d=json.loads(p.read_text()); d["branch"]="replacement"; p.write_text(json.dumps(d))' "$ROOT_DIR"
    return 1
  fi
}
''')
    for name in ('agent_preflight.sh', 'agent_guard.sh', 'db_backup.sh', 'db_verify_backup.sh'):
        (scripts / name).write_text('#!/usr/bin/env bash\n[[ "${FAIL_ACTION:-}" != "' + name + '" ]]\n')
        (scripts / name).chmod(0o755)
    package = scripts.parent / 'agent_hub'
    package.mkdir()
    (package / '__init__.py').write_text('')
    (package / 'context_receipt.py').write_text('')
    repo = tmp_path / 'repo'
    repo.mkdir()
    env = os.environ.copy()
    env.update(TEST_PYTHON=sys.executable, PYTHONPATH=str(scripts.parent))
    return scripts.parent, repo, env


def run(hub, script, *args, cwd=None, **env):
    root, repo, base = hub
    return subprocess.run(['bash', str(root / 'scripts' / script), *args], cwd=cwd or repo,
                          env={**base, **env}, text=True, capture_output=True)


def start(hub, *args, **kwargs):
    return run(hub, 'agent_start.sh', '--project', 'example', *args, **kwargs)


def lock(hub, repo=None):
    root, default, _ = hub
    key = hashlib.sha256(str((repo or default).resolve()).encode()).hexdigest()
    return root / '.local/run-locks' / f'{key}.lock'


def started(hub, *args, **kwargs):
    result = start(hub, *args, **kwargs)
    assert result.returncode == 0, result.stderr
    match = re.search(r'run_id: ([a-f0-9-]+)', result.stdout)
    assert match, 'successful start must return a run_id for finish'
    return match.group(1)


def status(hub, *args):
    result = run(hub, 'agent_lock_status.sh', *args, cwd=hub[1] if hub[1].exists() else hub[0])
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def recover(hub, digest, *args):
    return run(hub, 'agent_lock_recover.sh', '--repo', str(hub[1]), '--digest', digest,
               '--reason', 'reviewed interrupted fixture', *args, cwd=hub[1] if hub[1].exists() else hub[0])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_start_persists_unique_run_and_only_exact_finish_releases(hub):
    first = started(hub)
    data = json.loads(lock(hub).read_text())
    assert data['run_id'] == first
    assert data['project'] == 'example'
    assert data['repo_path'] == str(hub[1].resolve())
    assert all(k in data for k in ('branch', 'start_head', 'created_at', 'created_epoch'))
    assert start(hub).returncode != 0
    before = lock(hub).read_bytes()
    effects_before = (hub[0] / 'effects').read_text()
    for args in ([], ['--run-id', 'wrong'], ['--run-id', first, '--project', 'other']):
        result = run(hub, 'agent_finish.sh', '--project', 'example', *args, '--write-report')
        assert result.returncode != 0
        assert lock(hub).read_bytes() == before
        assert (hub[0] / 'effects').read_text() == effects_before
    assert not (hub[0] / 'effects').read_text().count('--write-report')
    result = run(hub, 'agent_finish.sh', '--project', 'example', '--run-id', first)
    assert result.returncode == 0, result.stderr
    assert not lock(hub).exists()
    archives = list((hub[0] / '.local/run-locks/.archive').glob('*/original.lock'))
    assert [p.read_bytes() for p in archives] == [before]
    assert started(hub) != first


def test_symlink_alias_collides_but_independent_worktree_does_not(hub, tmp_path):
    started(hub)
    alias = tmp_path / 'alias'
    alias.symlink_to(hub[1], target_is_directory=True)
    assert start(hub, cwd=alias).returncode != 0
    other = tmp_path / 'other'
    other.mkdir()
    assert start(hub, cwd=other).returncode == 0
    assert lock(hub, other).exists()


def test_no_lock_never_creates_or_releases(hub):
    assert start(hub, '--no-lock').returncode == 0
    assert not lock(hub).exists()
    started(hub)
    original = lock(hub).read_bytes()
    assert start(hub, '--no-lock').returncode == 0
    assert run(hub, 'agent_finish.sh', '--project', 'example', '--no-lock').returncode == 0
    assert lock(hub).read_bytes() == original


def test_failed_start_releases_own_run_and_failed_finish_keeps_it(hub):
    assert start(hub, FAIL_ACTION='compile').returncode != 0
    assert not lock(hub).exists()
    run_id = started(hub)
    original = lock(hub).read_bytes()
    for failure in ('daily', 'handoff', 'review', 'export', 'db_backup.sh', 'db_verify_backup.sh', 'actions'):
        result = run(hub, 'agent_finish.sh', '--project', 'example', '--run-id', run_id,
                     '--review', '--export', '--backup', FAIL_ACTION=failure)
        assert result.returncode != 0
        assert 'Agent finish result:' not in result.stdout
        assert lock(hub).read_bytes() == original


def test_offline_retry_retains_ownership_and_safe_argument_quoting(hub):
    run_id = started(hub)
    for mode in (['--run-id', run_id], ['--no-lock']):
        result = run(hub, 'agent_finish.sh', '--project', 'example', *mode,
                     '--since', '2026-09-01 01:00', FAIL_ACTION='agent_preflight.sh')
        assert result.returncode != 0
        note = (hub[0] / '.local/offline-finish/example-latest.md').read_text()
        retry = note.split('```bash\n')[1].split('\n')[0]
        tokens = shlex.split(retry)
        assert tokens[tokens.index('--since') + 1] == '2026-09-01 01:00'
        for item in mode:
            assert item in tokens
        assert lock(hub).exists()


def legacy(hub, created='1', repo=None):
    path = lock(hub)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'project=example\nrepo={repo or hub[1]}\nbranch=old\nhead=abc\ncreated_at=2000-01-01T00:00:00Z\ncreated_epoch={created}\n')
    return path


def test_legacy_blocks_start_even_stale_and_needs_explicit_recovery(hub):
    path = legacy(hub)
    original = path.read_bytes()
    assert start(hub).returncode != 0
    state = status(hub)
    assert state['owner_status'] == 'ownerless/legacy'
    assert state['stale'] is True and state['orphaned'] is False
    assert state['digest'] == digest(path)
    preview = run(hub, 'agent_lock_recover.sh', '--repo', str(hub[1]))
    assert preview.returncode == 0
    assert path.read_bytes() == original
    assert recover(hub, digest(path)).returncode != 0
    assert recover(hub, digest(path), '--acknowledge-legacy').returncode == 0
    assert not path.exists()
    archived = list(path.parent.glob('.archive/*/original.lock'))
    assert [p.read_bytes() for p in archived] == [original]
    assert list(path.parent.glob('.archive/*/completed.json'))


def test_stale_and_orphan_are_independent_and_invalid_age_unknown(hub):
    path = legacy(hub, created='invalid')
    hub[1].rmdir()
    state = status(hub, '--key', path.stem)
    assert state['stale'] is None and state['orphaned'] is True
    assert recover(hub, digest(path), '--acknowledge-legacy').returncode == 0


def test_unknown_owner_requires_ack_and_changed_snapshot_is_rejected(hub):
    started(hub)
    state = status(hub)
    assert state['owner_status'] == 'unknown-owner'
    assert recover(hub, state['digest']).returncode != 0
    data = json.loads(lock(hub).read_text())
    data['branch'] = 'changed'
    lock(hub).write_text(json.dumps(data))
    assert recover(hub, state['digest'], '--acknowledge-unknown').returncode != 0
    assert lock(hub).exists()
    assert recover(hub, digest(lock(hub)), '--acknowledge-unknown').returncode == 0


def test_live_owner_recovery_rejected_even_if_stale_and_orphaned(hub):
    started(hub, '--owner-pid', str(os.getpid()))
    data = json.loads(lock(hub).read_text())
    data['created_epoch'] = 1
    lock(hub).write_text(json.dumps(data))
    hub[1].rmdir()
    state = status(hub, '--key', lock(hub).stem)
    assert state['owner_status'] == 'owned/active'
    assert state['stale'] is True and state['orphaned'] is True
    result = run(hub, 'agent_lock_recover.sh', '--key', lock(hub).stem,
                 '--digest', digest(lock(hub)), '--reason', 'stale fixture', '--acknowledge-unknown', cwd=hub[0])
    assert result.returncode != 0
    assert lock(hub).exists()


def test_dead_owner_and_pid_reuse_are_not_active(hub):
    owner = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        started(hub, '--owner-pid', str(owner.pid))
    finally:
        owner.terminate()
        owner.wait()
    assert status(hub)['owner_status'] == 'dead-owner'
    assert recover(hub, digest(lock(hub))).returncode == 0
    started(hub, '--owner-pid', str(os.getpid()))
    data = json.loads(lock(hub).read_text())
    birth = data['owner']['process_start'].split(':')
    birth[0] = str(int(birth[0]) + 1)
    data['owner']['process_start'] = ':'.join(birth)
    lock(hub).write_text(json.dumps(data))
    assert status(hub)['owner_status'] == 'dead-owner'


def test_remote_owner_is_unknown_not_dead(hub):
    started(hub, '--owner-pid', str(os.getpid()))
    data = json.loads(lock(hub).read_text())
    data['owner']['host'] = 'different-host'
    lock(hub).write_text(json.dumps(data))
    assert status(hub)['owner_status'] == 'unknown-owner'
    assert recover(hub, digest(lock(hub))).returncode != 0


@pytest.mark.parametrize('kind', ['empty', 'malformed', 'symlink', 'directory', 'broken-owner'])
def test_corrupt_or_nonregular_locks_fail_closed(hub, kind):
    path = legacy(hub)
    if kind in ('empty', 'malformed'):
        path.write_text('' if kind == 'empty' else 'nonsense')
    elif kind in ('symlink', 'directory'):
        saved = path.with_suffix('.saved')
        path.rename(saved)
        if kind == 'symlink':
            path.symlink_to(saved)
        else:
            path.mkdir()
    else:
        path.rename(path.with_suffix('.saved'))
        started(hub)
        data = json.loads(path.read_text())
        data['owner'] = {'kind': 'pid', 'pid': 'invalid'}
        path.write_text(json.dumps(data))
    assert start(hub).returncode != 0
    result = recover(hub, '0' * 64 if not path.is_file() else digest(path),
                     '--acknowledge-legacy', '--acknowledge-unknown')
    assert result.returncode != 0
    assert path.exists()


def test_archive_failure_leaves_exact_lock(hub):
    path = legacy(hub)
    original = path.read_bytes()
    (path.parent / '.archive').write_text('not a directory')
    assert recover(hub, digest(path), '--acknowledge-legacy').returncode != 0
    assert path.read_bytes() == original


def test_concurrent_starts_have_one_winner(hub):
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: start(hub), range(8)))
    assert sum(r.returncode == 0 for r in results) == 1
    assert json.loads(lock(hub).read_text())['run_id']


def test_concurrent_recoveries_cannot_remove_replacement(hub):
    path = legacy(hub)
    snapshot = digest(path)
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: recover(hub, snapshot, '--acknowledge-legacy'), range(6)))
    assert sum(r.returncode == 0 for r in results) == 1
    run_id = started(hub)
    assert recover(hub, snapshot, '--acknowledge-legacy', '--acknowledge-unknown').returncode != 0
    assert json.loads(path.read_text())['run_id'] == run_id


def test_unsafe_flags_cannot_mutate_locks(hub):
    path = legacy(hub)
    original = path.read_bytes()
    assert start(hub, '--force-lock').returncode != 0
    assert run(hub, 'agent_lock_status.sh', '--all', '--clean-orphaned').returncode != 0
    assert path.read_bytes() == original


def test_failed_start_cleanup_cannot_remove_changed_snapshot(hub):
    result = start(hub, REPLACE_ON_ACTION='compile')
    assert result.returncode != 0
    assert lock(hub).exists()
    assert json.loads(lock(hub).read_text())['branch'] == 'replacement'


def test_finish_release_rechecks_snapshot_after_effects(hub):
    run_id = started(hub)
    # A successful external action changes the snapshot before final release.
    common = hub[0] / 'scripts/db_common.sh'
    common.write_text(common.read_text().replace('    return 1\n  fi\n}', '    return 0\n  fi\n}'))
    result = run(hub, 'agent_finish.sh', '--project', 'example', '--run-id', run_id,
                 REPLACE_ON_ACTION='actions')
    assert result.returncode != 0
    assert 'Agent finish result:' not in result.stdout
    assert lock(hub).exists()
    assert json.loads(lock(hub).read_text())['branch'] == 'replacement'


def load_helper():
    import importlib.util
    spec = importlib.util.spec_from_file_location('run_lock_test_module', ROOT / 'scripts/agent_run_lock.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_write_failure_preserves_lock_bytes(hub, monkeypatch):
    module = load_helper()
    path = legacy(hub)
    before = path.read_bytes()
    original_write = module.durable_write
    def fail_audit(target, raw):
        if target.name == 'prepared.json':
            raise OSError('fixture audit disk failure')
        return original_write(target, raw)
    monkeypatch.setattr(module, 'durable_write', fail_audit)
    with pytest.raises(OSError, match='audit disk failure'):
        with module.guard(path.parent, path.stem):
            module.archive_remove(path, module.read_snapshot(path), 'recovery', 'fixture')
    assert path.read_bytes() == before
    assert not list(path.parent.glob('.archive/*/completed.json'))


def test_malformed_birth_identity_cannot_bypass_active_owner(hub):
    started(hub, '--owner-pid', str(os.getpid()))
    data = json.loads(lock(hub).read_text())
    data['owner']['process_start'] = 'invalid'
    lock(hub).write_text(json.dumps(data))
    assert recover(hub, digest(lock(hub)), '--acknowledge-unknown').returncode != 0
    assert lock(hub).exists()


def test_status_and_preview_do_not_create_lock_directory(hub):
    assert status(hub)['status'] == 'unlocked'
    assert run(hub, 'agent_lock_recover.sh').returncode == 0
    assert not lock(hub).parent.exists()


def test_mutations_wait_on_same_permanent_guard(hub):
    import fcntl
    path = legacy(hub)
    guards = path.parent / '.guards'
    guards.mkdir()
    guard_path = guards / path.stem
    with guard_path.open('w') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        inode = guard_path.stat().st_ino
        root, repo, env = hub
        recovery = subprocess.Popen(['bash', str(root / 'scripts/agent_lock_recover.sh'),
            '--repo', str(repo), '--digest', digest(path), '--reason', 'fixture contention',
            '--acknowledge-legacy'], cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        acquisition = subprocess.Popen(['bash', str(root / 'scripts/agent_start.sh'), '--project', 'example'],
            cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # A held OS lock guarantees neither contender can finish, independent of scheduling.
        for proc in (recovery, acquisition):
            with pytest.raises(subprocess.TimeoutExpired):
                proc.wait(timeout=0.2)
        assert path.exists()
        fcntl.flock(held, fcntl.LOCK_UN)
        recovery.communicate(timeout=10)
        acquisition.communicate(timeout=10)
    assert recovery.returncode == 0
    assert guard_path.stat().st_ino == inode
    if acquisition.returncode == 0:
        assert json.loads(path.read_text())['run_id']
    else:
        assert not path.exists()


def test_unreaped_terminated_owner_is_dead(hub):
    import signal
    import time
    owner = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        started(hub, '--owner-pid', str(owner.pid))
        os.kill(owner.pid, signal.SIGKILL)
        time.sleep(0.1)
        assert status(hub)['owner_status'] == 'dead-owner'
    finally:
        owner.wait()


def test_recovery_rechecks_owner_after_preparing_archive(hub, monkeypatch):
    module = load_helper()
    started(hub)
    path = lock(hub)
    states = iter(['unknown-owner', 'owned/active'])
    monkeypatch.setattr(module, 'owner_status', lambda data: next(states))
    monkeypatch.setattr(sys, 'argv', ['lock-helper', '--lock-dir', str(path.parent),
        'recover', '--repo', str(hub[1]), '--digest', digest(path), '--reason', 'fixture', '--acknowledge-unknown'])
    with pytest.raises(module.LockError, match='active owner'):
        module.main()
    assert path.exists()


@pytest.mark.parametrize('preflight_error,expected', [
    ('Operational warning: docker is not available.\nTrying direct read-only Hub check through DATABASE_URL.\nOperational error: direct Hub check failed.', 0),
    ('Operational warning: docker is not available.\nTrying direct read-only Hub check through DATABASE_URL.\nUnexpected failure.', 1),
])
def test_offline_smoke_accepts_failed_direct_check_but_not_arbitrary_failure(hub, preflight_error, expected):
    root, _, _ = hub
    shutil.copy2(ROOT / 'scripts/smoke_agent_offline.sh', root / 'scripts/smoke_agent_offline.sh')
    (root / 'scripts/agent_preflight.sh').write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" ' + shlex.quote(preflight_error) + '\nexit 2\n')
    result = run(hub, 'smoke_agent_offline.sh')
    assert result.returncode == expected, result.stdout + result.stderr
    if expected == 0:
        assert 'Offline-agent smoke: ok' in result.stdout
    else:
        assert 'Expected a known offline preflight reason.' in result.stderr
