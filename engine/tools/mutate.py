#!/usr/bin/env python3
"""Run a stage's mutation suite: prove its checks can fail.

    python engine/tools/mutate.py r1 [--keep] [name-substring ...]

docs/c17-rewrite-plan.md section 4: every stage after R.0 has a list of
single edits to the rewrite, and the stage's checks must fail on every
one. A verifier that cannot fail proves nothing. The lists are in
engine/tools/mutants/<stage>.py; this is the driver they share. The
mutants are klattsch's kind (tools/stage*-mutations.py there): literal
find-and-replace, one edit each. klattsch edits its tree in place and
restores it; this driver mutates a copy instead, so an interrupted run
cannot leave a mutant in the working tree.

What it does:

  1. Copies engine/, native/ (its tools and golden vectors) and the
     Python under nvda-addon/ into a scratch directory, leaving out
     build trees and packaged files.
  2. Configures the copy once with MSVC and Ninja, builds it, and runs
     every check on the unmutated copy. All must pass; otherwise the
     suite stops, since a check that already fails cannot be killed.
  3. For each mutant: applies its edits, rebuilds, runs every check,
     and puts the files back. A check kills the mutant when it exits
     with anything but 0 (passed) or 77 (skipped, which is reported as
     an error: the check did not run). A mutant that does not build is
     an error too; every mutant must be a program the checks can see.

Each mutant names the checks expected to kill it, and the result must
match exactly. Mutants that only some checks can see are the point:
an edit to a comment in a generated header is invisible to the value
verifier and caught by the generator's --check, and the other way round
for an edit to a dump tool. The table this prints is what each stage's
chapter in docs/c17/ quotes.

Exit 0 when every mutant was killed by exactly its expected checks,
1 otherwise, 2 on a usage or setup error. --keep leaves the scratch
copy in place and prints where it is.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, os.path.join(ROOT, 'native', 'tools'))
from _build import SKIP, find_vs  # noqa: E402

# What is copied, relative to the repository root, and what is left out.
COPY = ('engine', 'native', 'nvda-addon')
IGNORE = shutil.ignore_patterns('build', 'build-*', '__pycache__',
                                '*.nvda-addon', '*.zip', '*.dll', '*.exe')


def load_stage(stage):
    path = os.path.join(ENGINE, 'tools', 'mutants', stage + '.py')
    if not os.path.exists(path):
        raise SystemExit('no mutant list %s' % os.path.relpath(path, ROOT))
    spec = importlib.util.spec_from_file_location('mutants_' + stage, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def msvc_env():
    """The environment of an x64 developer prompt, as a dict."""
    vs = find_vs()
    if vs is None:
        raise SystemExit('no Visual Studio found')
    vcvars = os.path.join(vs, 'VC', 'Auxiliary', 'Build', 'vcvarsall.bat')
    out = subprocess.run('call "%s" x64 >nul 2>nul && set' % vcvars,
                         shell=True, capture_output=True, text=True,
                         errors='replace').stdout
    env = dict(line.split('=', 1) for line in out.splitlines() if '=' in line)
    if 'VCINSTALLDIR' not in env:
        raise SystemExit('vcvarsall did not set up a developer environment')
    return env


def read(path):
    with open(path, encoding='utf-8', newline='') as fh:
        raw = fh.read()
    return raw, '\r\n' in raw


def write(path, text, crlf):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text.replace('\n', '\r\n') if crlf else text)


def apply(copy, edits):
    """Apply (path, find, replace) edits; return what to put back.

    find must occur exactly once, after CRLF is read as LF, so a mutant
    whose anchor has drifted is an error rather than a silent no-op.
    """
    saved = {}
    for rel, find, replace in edits:
        path = os.path.join(copy, rel)
        if path not in saved:
            saved[path] = read(path)[0]
        raw, crlf = read(path)
        text = raw.replace('\r\n', '\n')
        n = text.count(find)
        if n != 1:
            restore(saved)
            return None, '%s: anchor found %d times, not once' % (rel, n)
        write(path, text.replace(find, replace), crlf)
    return saved, None


def restore(saved):
    for path, raw in saved.items():
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(raw)


def build(env, build_dir):
    r = subprocess.run(['cmake', '--build', build_dir], env=env,
                       capture_output=True, text=True, errors='replace')
    return r.returncode == 0, r.stdout + r.stderr


def run_checks(checks, copy, env):
    """{name: 'pass' | 'fail' | 'skip'} for every check."""
    result = {}
    for name, argv in checks.items():
        args = [a.replace('{copy}', copy) for a in argv]
        r = subprocess.run([sys.executable] + args, cwd=copy, env=env,
                           capture_output=True, text=True, errors='replace')
        result[name] = ('pass' if r.returncode == 0 else
                        'skip' if r.returncode == SKIP else 'fail')
    return result


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    keep = '--keep' in argv
    if not args:
        print(__doc__)
        return 2
    stage = load_stage(args[0])
    wanted = args[1:]
    mutants = [m for m in stage.MUTANTS
               if not wanted or any(w in m['name'] for w in wanted)]

    scratch = tempfile.mkdtemp(prefix='sam-mutants-')
    copy = os.path.join(scratch, 'sam')
    try:
        for d in COPY:
            shutil.copytree(os.path.join(ROOT, d), os.path.join(copy, d),
                            ignore=IGNORE)
        env = msvc_env()
        build_dir = os.path.join(copy, 'engine', 'build-mutants')
        env['SAM_ENGINE_BUILD'] = build_dir
        r = subprocess.run(['cmake', '-S', os.path.join(copy, 'engine'),
                            '-B', build_dir, '-G', 'Ninja',
                            '-DCMAKE_C_COMPILER=cl', '-DBUILD_TESTING=ON'],
                           env=env, capture_output=True, text=True,
                           errors='replace')
        if r.returncode != 0:
            print(r.stdout[-3000:] + r.stderr[-3000:])
            print('configure failed')
            return 2
        ok, log = build(env, build_dir)
        if not ok:
            print(log[-3000:])
            print('the unmutated copy does not build')
            return 2

        base = run_checks(stage.CHECKS, copy, env)
        print('unmutated: ' + ', '.join('%s %s' % kv for kv in base.items()))
        if any(v != 'pass' for v in base.values()):
            print('every check must pass on the unmutated copy first')
            return 2
        print()

        rows = []
        for m in mutants:
            saved, why = apply(copy, m['edits'])
            if saved is None:
                rows.append((m, None, why))
                continue
            try:
                ok, log = build(env, build_dir)
                if not ok:
                    rows.append((m, None, 'did not build'))
                    continue
                res = run_checks(stage.CHECKS, copy, env)
            finally:
                restore(saved)
            skipped = [k for k, v in res.items() if v == 'skip']
            if skipped:
                rows.append((m, None, 'skipped: ' + ', '.join(skipped)))
                continue
            rows.append((m, {k for k, v in res.items() if v == 'fail'}, None))

        # Leave the build matching the unmutated sources, for --keep.
        build(env, build_dir)

        bad = 0
        width = max(len(m['name']) for m, _, _ in rows)
        names = list(stage.CHECKS)
        print('%-*s  %s' % (width, 'mutant', '  '.join(names)))
        for m, killed, why in rows:
            if killed is None:
                bad += 1
                print('%-*s  ERROR %s' % (width, m['name'], why))
                continue
            expect = set(m['killed_by'])
            cells = '  '.join(('killed' if n in killed else 'lived').ljust(len(n))
                              for n in names)
            verdict = 'ok' if killed == expect else 'UNEXPECTED'
            if killed != expect:
                bad += 1
            print('%-*s  %s  %s' % (width, m['name'], cells, verdict))
        print()
        print('%d mutants, %d as expected, %d not'
              % (len(rows), len(rows) - bad, bad))
        return 1 if bad else 0
    finally:
        if keep:
            print('scratch copy kept: %s' % copy)
        else:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
