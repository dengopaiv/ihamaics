"""Package SAM NVDA addon into .nvda-addon file."""
import zipfile
import os

addon_dir = os.path.dirname(os.path.abspath(__file__))
output_file = os.path.join(addon_dir, 'sam.nvda-addon')

SKIP_DIRS = {'__pycache__'}


def clean_cmudict(content):
    """Strip alternate pronunciations, inline comments, and blank lines from cmudict."""
    lines = content.splitlines()
    cleaned = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith(';;;'):
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
    manifest_bytes = manifest_content.encode('utf-8')
    total_original += len(manifest_bytes)
    total_cleaned += len(manifest_bytes)
    zf.writestr('manifest.ini', manifest_bytes)
    print(f'Added: manifest.ini')

    # Add synthDrivers directory
    synth_dir = os.path.join(addon_dir, 'synthDrivers', 'sam')
    for dirpath, dirnames, filenames in os.walk(synth_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in sorted(filenames):
            if filename.startswith('test_') or filename.endswith('_test.py'):
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

print(f'\nTotal content: {total_original/1024:.1f} KB -> {total_cleaned/1024:.1f} KB (saved {(total_original-total_cleaned)/1024:.1f} KB)')
print(f'Created: {output_file}')
print(f'Archive size: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB')

# List contents
print('\nAddon contents:')
with zipfile.ZipFile(output_file, 'r') as zf:
    for info in zf.infolist():
        size_kb = info.file_size / 1024
        print(f'  {info.filename}: {size_kb:.1f} KB')
