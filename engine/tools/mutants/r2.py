"""Stage R.2 mutants: the voice (docs/c17/02-r2-voice.md).

Run with: python engine/tools/mutate.py r2

Two checks, and the compiler:

  verify_frames   sam_set_mouth_throat for all 65,536 (mouth, throat)
                  pairs, through engine/tools/dump_frames.c, against
                  set_mouth_throat() in renderer.py;
  tables_current  the generated tables, SAM_FREQ_MAX included, against
                  what engine/tools/gen_tables.py would write now;
  build           (killed_by only) the edit must not compile: the
                  _Static_assert in voice.c refuses it.

Each mutant is one edit, and killed_by names exactly what must fail.
Two mutants are expected to live, because they change nothing any
input can see: the Python's & 0xFF, which section 2.2 of the chapter
says no input reaches, and the diphthong range starting at 47.
"""

CHECKS = {
    'verify_frames': ['native/tools/verify_frames.py', '--impl', 'engine'],
    'tables_current': ['engine/tools/gen_tables.py', '--check'],
}

V = 'engine/src/voice.c'
H = 'engine/src/tables.h'
T = 'engine/src/tables.c'
D = 'engine/tools/dump_frames.c'
PY = 'nvda-addon/synthDrivers/sam/renderer.py'
PYT = 'nvda-addon/synthDrivers/sam/renderer_tables.py'

FRAMES = ('verify_frames',)
BOTH = ('verify_frames', 'tables_current')

MUTANTS = [
    # Which phonemes a voice alters: each end of each range, by one.
    dict(name='first voiced phoneme 5 -> 4',
         edits=[(V, '#define VOICED_FIRST     5', '#define VOICED_FIRST     4')],
         killed_by=FRAMES),
    dict(name='voiced range ends at 29, not 30',
         edits=[(V, '#define VOICED_END      30', '#define VOICED_END      29')],
         killed_by=FRAMES),
    dict(name='first diphthong 48 -> 49',
         edits=[(V, '#define DIPHTHONG_FIRST 48', '#define DIPHTHONG_FIRST 49')],
         killed_by=FRAMES),
    # Phoneme 47 ('**') has all three frequencies 0, and 0 scales to 0,
    # so starting the range one early changes nothing for any voice.
    dict(name='first diphthong 48 -> 47 (equivalent: ** is all 0)',
         edits=[(V, '#define DIPHTHONG_FIRST 48', '#define DIPHTHONG_FIRST 47')],
         killed_by=()),
    dict(name='diphthong range ends at 55, not 54',
         edits=[(V, '#define DIPHTHONG_END   54', '#define DIPHTHONG_END   55')],
         killed_by=FRAMES),
    dict(name='diphthongs not scaled at all',
         edits=[(V, '    scale_range(mouth, throat, out, DIPHTHONG_FIRST, DIPHTHONG_END);\n',
                 '')],
         killed_by=FRAMES),

    # The transform itself.
    dict(name='scale not doubled',
         edits=[(V, '>> 8) << 1);', '>> 8));')],
         killed_by=FRAMES),
    dict(name='scale shifts by 7, not 8 (wraps in a byte)',
         edits=[(V, '>> 8) << 1);', '>> 7) << 1);')],
         killed_by=FRAMES),
    dict(name='mouth and throat swapped',
         edits=[(V, 'fd->f1[i] = scale(mouth, fd->f1[i]);\n        fd->f2[i] = scale(throat, fd->f2[i]);',
                 'fd->f1[i] = scale(throat, fd->f1[i]);\n        fd->f2[i] = scale(mouth, fd->f2[i]);')],
         killed_by=FRAMES),
    dict(name='formant 3 scaled by mouth too',
         edits=[(V, '        fd->f2[i] = scale(throat, fd->f2[i]);\n',
                 '        fd->f2[i] = scale(throat, fd->f2[i]);\n'
                 '        fd->f3[i] = scale(mouth, fd->f3[i]);\n')],
         killed_by=FRAMES),
    dict(name='formant 3 copied from sam_freq2',
         edits=[(V, 'memcpy(out->f3, sam_freq3,', 'memcpy(out->f3, sam_freq2,')],
         killed_by=FRAMES),

    # The tables underneath.
    dict(name='tables.c: NX F2 86 -> 200 by hand',
         edits=[(T, '54,   86,   54,', '54,  200,   54,')],
         killed_by=BOTH),
    dict(name='Python: NX F2 86 -> 87, not regenerated',
         edits=[(PYT, '0x793606, 0x655606,', '0x793606, 0x655706,')],
         killed_by=BOTH),

    # The bound. A table with a frequency above 128 would not fit in a
    # byte once scaled, and the build must refuse it.
    dict(name='SAM_FREQ_MAX 127 -> 129',
         edits=[(H, '#define SAM_FREQ_MAX                 127',
                 '#define SAM_FREQ_MAX                 129')],
         killed_by=('build',)),
    dict(name='SAM_FREQ_MAX 127 -> 128 (still fits)',
         edits=[(H, '#define SAM_FREQ_MAX                 127',
                 '#define SAM_FREQ_MAX                 128')],
         killed_by=('tables_current',)),

    # The idiom section 2.2 drops: removing it from the oracle changes
    # nothing, so this mutant lives, and that is the claim.
    dict(name="Python trans() without & 0xFF (equivalent)",
         edits=[(PY, 'return (((factor * initial_frequency) >> 8) & 0xFF) << 1',
                 'return ((factor * initial_frequency) >> 8) << 1')],
         killed_by=()),

    # The dump tool lying.
    dict(name='dump hashes the high byte as 1',
         edits=[(D, 'h = fnv1a(h, 0);', 'h = fnv1a(h, 1);')],
         killed_by=FRAMES),
    dict(name='dump stops at throat 254',
         edits=[(D, 'throat < 256;', 'throat < 255;')],
         killed_by=FRAMES),
    dict(name='dump skips formant 3',
         edits=[(D, 'r < 3;', 'r < 2;')],
         killed_by=FRAMES),
]
