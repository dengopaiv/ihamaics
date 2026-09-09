#!/usr/bin/env python3
"""Build the CMU dictionary blob the C front end searches.

    python native/tools/gen_dict.py

Writes native/data/sam.dict from
nvda-addon/synthDrivers/sam/cmudict.txt, parsed by the addon's own
cmudict.py so that the blob contains exactly what Python would look up -
including the sixteen entries whose trailing "# place, danish" comment
cmudict.py stores as if it were part of the pronunciation. Reproducing
that is the point: the C side has to agree with the Python side, not
with the CMU file.

The dictionary is 126k entries and several megabytes of strings. As a C
array that is tens of megabytes of source and a minute of compiler time
for data that never needs compiling, so it ships as a binary blob
instead: the GUI embeds it as a Windows resource and hands the engine a
pointer, and the verification tools read the file. Either way the engine
only ever sees a const buffer it does not own, never copies it and never
frees it.

Layout, all little-endian:

    magic     8            "SAMDIC\\0" + format version byte
    count     4            number of entries
    pool_len  4            size of the string pool
    offsets   4 * count    byte offset of each entry within the pool
    pool      pool_len     "WORD\\0PHONEMES\\0" per entry

PHONEMES is the ARPABET tokens joined with single spaces, which is what
cmudict.py holds as a list. Entries are sorted by word so the C side can
binary search. Every key is ASCII, which is why a C byte comparison and
Python's own string ordering agree; this script checks that rather than
assuming it.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import cmudict  # noqa: E402

OUT_DIR = os.path.join(ROOT, 'native', 'data')
OUT = os.path.join(OUT_DIR, 'sam.dict')

MAGIC = b'SAMDIC\x00\x01'


def main():
    table = cmudict.load_cmudict()
    if not table:
        raise SystemExit('cmudict.txt produced no entries; is it present?')

    words = sorted(table)

    for w in words:
        if not w.isascii():
            raise SystemExit('non-ASCII key would break byte ordering: %r' % w)
        if '\x00' in w:
            raise SystemExit('NUL in key: %r' % w)
    encoded = [w.encode('ascii') for w in words]
    if encoded != sorted(encoded):
        raise SystemExit('byte ordering disagrees with Python string ordering')

    offsets = []
    pool = bytearray()
    for w in words:
        pron = ' '.join(table[w])
        if not pron.isascii() or '\x00' in pron:
            raise SystemExit('bad pronunciation for %r: %r' % (w, pron))
        offsets.append(len(pool))
        pool += w.encode('ascii') + b'\x00'
        pool += pron.encode('ascii') + b'\x00'

    blob = bytearray()
    blob += MAGIC
    blob += struct.pack('<II', len(words), len(pool))
    blob += struct.pack('<%dI' % len(offsets), *offsets)
    blob += pool

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, 'wb') as f:
        f.write(blob)

    print('  entries   %d' % len(words))
    print('  offsets   %d bytes' % (len(offsets) * 4))
    print('  pool      %d bytes' % len(pool))
    print('  total     %d bytes (%.2f MiB)'
          % (len(blob), len(blob) / 1024 / 1024))
    print('\n-> %s' % os.path.relpath(OUT, ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
