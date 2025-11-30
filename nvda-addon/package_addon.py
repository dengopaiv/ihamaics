"""Package SAM NVDA addon into .nvda-addon file."""
import zipfile
import os

addon_dir = r'C:\git\sam\nvda-addon'
output_file = os.path.join(addon_dir, 'sam.nvda-addon')

# Remove old addon file if exists
if os.path.exists(output_file):
    os.remove(output_file)

with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
    # Add manifest.ini
    zf.write(os.path.join(addon_dir, 'manifest.ini'), 'manifest.ini')

    # Add synthDrivers directory
    synth_dir = os.path.join(addon_dir, 'synthDrivers', 'sam')
    for filename in os.listdir(synth_dir):
        filepath = os.path.join(synth_dir, filename)
        if os.path.isfile(filepath) and (filename.endswith('.py') or filename.endswith('.txt')):
            arcname = f'synthDrivers/sam/{filename}'
            zf.write(filepath, arcname)
            print(f'Added: {arcname}')

print(f'\nCreated: {output_file}')
print(f'Size: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB')

# List contents
print('\nAddon contents:')
with zipfile.ZipFile(output_file, 'r') as zf:
    for info in zf.infolist():
        size_kb = info.file_size / 1024
        print(f'  {info.filename}: {size_kb:.1f} KB')
