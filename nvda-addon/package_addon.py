"""Package the SAM NVDA addon into a .nvda-addon file.

    python nvda-addon/package_addon.py                     the shipped addon
    python nvda-addon/package_addon.py --python-fallback   with the Python renderer

The shipped addon is native only: the pure Python renderer and its
tables are left out, and renderer_native_only.py goes in as renderer.py,
so the C library is the only thing that can produce audio. With no
fallback, a library that fails to load raises instead of quietly
sounding identical but slower.

--python-fallback rebuilds the older shape, Python renderer included.
It is there for working on the port from a source checkout; it is not
what gets released. The Python renderer stays in the repository as the
reference the C engine is verified against.
"""
import sys
import time
import zipfile
import os

PYTHON_FALLBACK = '--python-fallback' in sys.argv[1:]
NATIVE_ONLY = not PYTHON_FALLBACK

addon_dir = os.path.dirname(os.path.abspath(__file__))
output_file = os.path.join(
    addon_dir,
    'sam-python-fallback.nvda-addon' if PYTHON_FALLBACK else 'sam.nvda-addon')

SKIP_DIRS = {'__pycache__'}

manifest_path = os.path.join(addon_dir, 'manifest.ini')
notice_path = os.path.join(os.path.dirname(addon_dir), 'NOTICE.md')
licence_path = os.path.join(os.path.dirname(addon_dir), 'LICENSE')
shim_path = os.path.join(addon_dir, 'renderer_native_only.py')
synth_dir = os.path.join(addon_dir, 'synthDrivers', 'sam')
build_dir = os.path.join(os.path.dirname(addon_dir), 'native', 'build')

# Omitted from a native-only build: the Python renderer and its tables.
NATIVE_ONLY_OMIT = {'renderer.py', 'renderer_tables.py'}


def clean_cmudict(content):
    """Strip alternate pronunciations, inline comments and blank lines from cmudict.

    The ;;; licence header is preserved verbatim.
    """
    lines = content.splitlines()
    cleaned = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith(';;;'):
            # Keep CMU's copyright notice: their licence requires that
            # redistributions retain it, and deems this file source code.
            cleaned.append(line)
            continue
        word_field = line.split()[0] if line.split() else ''
        if '(' in word_field:
            continue
        comment_pos = line.find(' #')
        if comment_pos != -1:
            line = line[:comment_pos]
        cleaned.append(line)
    return '\n'.join(cleaned) + '\n'


def clean_python(content):
    """Strip comment-only and blank lines from Python source."""
    lines = content.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped == '' or (stripped.startswith('#') and not stripped.startswith('#!')):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned) + '\n'


# Every entry gets one timestamp, taken from the newest input. zipfile
# would otherwise stamp "now" on each build, and the addon is packed
# into sam-native.zip, which is tracked - an unchanged tree has to
# rebuild to the same bytes rather than a fresh 3 MB diff.
def newest_input_time():
    paths = [manifest_path, notice_path, licence_path, shim_path]
    for dirpath, dirnames, filenames in os.walk(synth_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        paths += [os.path.join(dirpath, f) for f in filenames]
    for arch in ('x64', 'x86'):
        dll = os.path.join(build_dir, f'sam_render-{arch}.dll')
        if os.path.exists(dll):
            paths.append(dll)
    return time.localtime(max(os.path.getmtime(p) for p in paths))[:6]


def write(zf, name, data):
    info = zipfile.ZipInfo(name, STAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


STAMP = newest_input_time()

# Remove old addon file if exists
if os.path.exists(output_file):
    os.remove(output_file)

total_original = 0
total_cleaned = 0

with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
    # Add manifest.ini
    manifest_content = open(manifest_path, 'r', encoding='utf-8').read()
    if PYTHON_FALLBACK:
        # Distinguishable in NVDA's add-on list, so a fallback build that
        # got installed by accident is not mistaken for the release.
        manifest_content = manifest_content.replace(
            'summary = "SAM (Software Automatic Mouth) Synthesizer"',
            'summary = "SAM (Software Automatic Mouth) Synthesizer [python fallback]"')
        manifest_content = manifest_content.replace(
            'Speech is rendered by a native C engine.',
            'Uses a native renderer for low latency, falling back to pure '
            'Python if it cannot be loaded.')
    manifest_bytes = manifest_content.encode('utf-8')
    total_original += len(manifest_bytes)
    total_cleaned += len(manifest_bytes)
    write(zf, 'manifest.ini', manifest_bytes)
    print(f'Added: manifest.ini')

    # Ship the third-party notices with the addon (CMU's licence requires it)
    notice_bytes = open(notice_path, 'rb').read()
    total_original += len(notice_bytes)
    total_cleaned += len(notice_bytes)
    write(zf, 'NOTICE.md', notice_bytes)
    print(f'Added: NOTICE.md')

    # And the licence statement, so someone who unpacks the addon can see
    # the position without going to the repository.
    licence_bytes = open(licence_path, 'rb').read()
    total_original += len(licence_bytes)
    total_cleaned += len(licence_bytes)
    write(zf, 'LICENSE', licence_bytes)
    print(f'Added: LICENSE')

    # Add synthDrivers directory
    for dirpath, dirnames, filenames in os.walk(synth_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in sorted(filenames):
            if filename.startswith('test_') or filename.endswith('_test.py'):
                continue
            if NATIVE_ONLY and filename in NATIVE_ONLY_OMIT:
                print(f'Omitted: {filename} (native-only build)')
                continue
            if not (filename.endswith('.py') or filename.endswith('.txt')):
                continue

            filepath = os.path.join(dirpath, filename)
            relpath = os.path.relpath(filepath, addon_dir).replace('\\', '/')
            content = open(filepath, 'r', encoding='utf-8').read()
            original_size = len(content.encode('utf-8'))

            if filename.endswith('.txt'):
                content = clean_cmudict(content)
            elif filename.endswith('.py'):
                content = clean_python(content)

            cleaned_bytes = content.encode('utf-8')
            cleaned_size = len(cleaned_bytes)
            saved = original_size - cleaned_size

            write(zf, relpath, cleaned_bytes)
            total_original += original_size
            total_cleaned += cleaned_size

            if saved > 0:
                print(f'Added: {relpath} ({original_size/1024:.1f} KB -> {cleaned_size/1024:.1f} KB, saved {saved/1024:.1f} KB)')
            else:
                print(f'Added: {relpath} ({original_size/1024:.1f} KB)')

    # Native-only build: stand in a renderer.py that only calls the library.
    if NATIVE_ONLY:
        shim = clean_python(open(shim_path, 'r', encoding='utf-8').read())
        shim_bytes = shim.encode('utf-8')
        write(zf, 'synthDrivers/sam/renderer.py', shim_bytes)
        total_original += len(shim_bytes)
        total_cleaned += len(shim_bytes)
        print(f'Added: synthDrivers/sam/renderer.py '
              f'(from renderer_native_only.py, {len(shim_bytes)/1024:.1f} KB)')

    # Native renderer. Both architectures ship: NVDA is x64 now but
    # 32-bit builds still exist, and native.py picks at load time.
    # Missing DLLs are fatal for the shipped addon; for a fallback build
    # they only mean renderer.py takes the Python path.
    shipped_dlls = 0
    for arch in ('x64', 'x86'):
        dll_path = os.path.join(build_dir, f'sam_render-{arch}.dll')
        if not os.path.exists(dll_path):
            print(f'Skipped: sam_render-{arch}.dll (not built)')
            continue
        shipped_dlls += 1
        with open(dll_path, 'rb') as f:
            dll_bytes = f.read()
        write(zf, f'synthDrivers/sam/sam_render-{arch}.dll', dll_bytes)
        total_original += len(dll_bytes)
        total_cleaned += len(dll_bytes)
        print(f'Added: synthDrivers/sam/sam_render-{arch}.dll '
              f'({len(dll_bytes)/1024:.1f} KB)')

if NATIVE_ONLY and shipped_dlls == 0:
    os.remove(output_file)
    raise SystemExit('ERROR: a native-only build needs the DLLs. '
                     'Run native\\build.cmd first.')

print(f'\nTotal content: {total_original/1024:.1f} KB -> {total_cleaned/1024:.1f} KB (saved {(total_original-total_cleaned)/1024:.1f} KB)')
print(f'Created: {output_file}')
print(f'Archive size: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB')

# List contents
print('\nAddon contents:')
with zipfile.ZipFile(output_file, 'r') as zf:
    for info in zf.infolist():
        size_kb = info.file_size / 1024
        print(f'  {info.filename}: {size_kb:.1f} KB')
