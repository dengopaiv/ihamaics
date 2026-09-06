"""Package SAM NVDA addon into .nvda-addon file.

    python nvda-addon/package_addon.py                 standard build
    python nvda-addon/package_addon.py --native-only    C renderer only

The native-only build omits the pure Python renderer and its tables and
ships renderer_native_only.py as renderer.py, so the C library is the
only thing that can produce audio. It exists to prove which engine is
doing the work: with no fallback, a library that fails to load raises
instead of quietly sounding identical but slower.
"""
import sys
import zipfile
import os

NATIVE_ONLY = '--native-only' in sys.argv[1:]

addon_dir = os.path.dirname(os.path.abspath(__file__))
output_file = os.path.join(
    addon_dir, 'sam-native-only.nvda-addon' if NATIVE_ONLY else 'sam.nvda-addon')

SKIP_DIRS = {'__pycache__'}

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


# Remove old addon file if exists
if os.path.exists(output_file):
    os.remove(output_file)

total_original = 0
total_cleaned = 0

with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
    # Add manifest.ini
    manifest_path = os.path.join(addon_dir, 'manifest.ini')
    manifest_content = open(manifest_path, 'r', encoding='utf-8').read()
    if NATIVE_ONLY:
        # Distinguishable in NVDA's add-on list, and a higher version so it
        # installs cleanly over the standard build.
        manifest_content = manifest_content.replace(
            'summary = "SAM (Software Automatic Mouth) Synthesizer"',
            'summary = "SAM (Software Automatic Mouth) Synthesizer [native only]"')
        manifest_content = manifest_content.replace(
            'version = 1.4.0', 'version = 1.4.1')
    manifest_bytes = manifest_content.encode('utf-8')
    total_original += len(manifest_bytes)
    total_cleaned += len(manifest_bytes)
    zf.writestr('manifest.ini', manifest_bytes)
    print(f'Added: manifest.ini')

    # Ship the third-party notices with the addon (CMU's licence requires it)
    notice_path = os.path.join(os.path.dirname(addon_dir), 'NOTICE.md')
    notice_bytes = open(notice_path, 'rb').read()
    total_original += len(notice_bytes)
    total_cleaned += len(notice_bytes)
    zf.writestr('NOTICE.md', notice_bytes)
    print(f'Added: NOTICE.md')

    # And the licence statement, so someone who unpacks the addon can see
    # the position without going to the repository.
    licence_path = os.path.join(os.path.dirname(addon_dir), 'LICENSE')
    licence_bytes = open(licence_path, 'rb').read()
    total_original += len(licence_bytes)
    total_cleaned += len(licence_bytes)
    zf.writestr('LICENSE', licence_bytes)
    print(f'Added: LICENSE')

    # Add synthDrivers directory
    synth_dir = os.path.join(addon_dir, 'synthDrivers', 'sam')
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

            zf.writestr(relpath, cleaned_bytes)
            total_original += original_size
            total_cleaned += cleaned_size

            if saved > 0:
                print(f'Added: {relpath} ({original_size/1024:.1f} KB -> {cleaned_size/1024:.1f} KB, saved {saved/1024:.1f} KB)')
            else:
                print(f'Added: {relpath} ({original_size/1024:.1f} KB)')

    # Native-only build: stand in a renderer.py that only calls the library.
    if NATIVE_ONLY:
        shim_path = os.path.join(addon_dir, 'renderer_native_only.py')
        shim = clean_python(open(shim_path, 'r', encoding='utf-8').read())
        shim_bytes = shim.encode('utf-8')
        zf.writestr('synthDrivers/sam/renderer.py', shim_bytes)
        total_original += len(shim_bytes)
        total_cleaned += len(shim_bytes)
        print(f'Added: synthDrivers/sam/renderer.py '
              f'(from renderer_native_only.py, {len(shim_bytes)/1024:.1f} KB)')

    # Native renderer, if built. Both architectures ship: NVDA is x64 now
    # but 32-bit builds still exist, and native.py picks at load time.
    # Absent is not an error for the standard build - renderer.py falls
    # back to the Python path. For a native-only build it is fatal.
    build_dir = os.path.join(os.path.dirname(addon_dir), 'native', 'build')
    shipped_dlls = 0
    for arch in ('x64', 'x86'):
        dll_path = os.path.join(build_dir, f'sam_render-{arch}.dll')
        if not os.path.exists(dll_path):
            print(f'Skipped: sam_render-{arch}.dll (not built)')
            continue
        shipped_dlls += 1
        with open(dll_path, 'rb') as f:
            dll_bytes = f.read()
        zf.writestr(f'synthDrivers/sam/sam_render-{arch}.dll', dll_bytes)
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
