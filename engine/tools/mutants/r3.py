"""Stage R.3 mutants: the frames (docs/c17/03-r3-frames.md).

Run with: python engine/tools/mutate.py r3

One check:

  verify_prepare  sam_prepare_frames over the 16 golden cases and 3,000
                  random ones, through engine/tools/dump_prepare.c,
                  against prepare_frames() in renderer.py, all eight
                  rows and the frame count.

Each mutant is one edit, and killed_by names exactly what must fail.
The groups below follow the chapter's section 3.2:

  - SAM's own arithmetic, edited: every one must die.
  - The two quirks kept in quirks.h, "fixed" in the rewrite or in the
    oracle: each must die, which is what "the voice depends on it"
    means when it is run.
  - The idioms the rewrite dropped, removed from the oracle instead:
    each must live, which is "no input reaches it", run.
  - The dump tool lying.
"""

CHECKS = {
    'verify_prepare': ['native/tools/verify_prepare.py', '--impl', 'engine',
                       '3000'],
}

F = 'engine/src/frames.c'
Q = 'engine/src/quirks.h'
D = 'engine/tools/dump_prepare.c'
PY = 'nvda-addon/synthDrivers/sam/renderer.py'

KILLED = ('verify_prepare',)
LIVES = ()

MUTANTS = [
    # create_frames: inflection and stress.
    dict(name='inflection reaches 29 frames back, not 30',
         edits=[(F, '#define INFLECTION_REACH     30', '#define INFLECTION_REACH     29')],
         killed_by=KILLED),
    dict(name='first skipped pitch 127 -> 126',
         edits=[(F, '#define PITCH_SKIP_FIRST    127', '#define PITCH_SKIP_FIRST    126')],
         killed_by=KILLED),
    dict(name='later skipped pitch 255 -> 254',
         edits=[(F, '#define PITCH_SKIP_LATER    255', '#define PITCH_SKIP_LATER    254')],
         killed_by=KILLED),
    dict(name='rising inflection 255 -> 254',
         edits=[(F, '#define RISING_INFLECTION   255', '#define RISING_INFLECTION   254')],
         killed_by=KILLED),
    dict(name='falling inflection 1 -> 2',
         edits=[(F, '#define FALLING_INFLECTION    1', '#define FALLING_INFLECTION    2')],
         killed_by=KILLED),
    dict(name="'.' and '?' swapped",
         edits=[(F, 'add_inflection(fr->pitch, n, falling);', 'add_inflection(fr->pitch, n, RISING);'),
                (F, 'add_inflection(fr->pitch, n, rising);', 'add_inflection(fr->pitch, n, falling);'),
                (F, 'add_inflection(fr->pitch, n, RISING);', 'add_inflection(fr->pitch, n, rising);')],
         killed_by=KILLED),
    dict(name='rising inflection not clamped to 255',
         edits=[(F, '    rising = (rising > UINT8_MAX) ? UINT8_MAX : rising;\n', '')],
         killed_by=KILLED),
    dict(name='stress pitch not scaled by inflection',
         edits=[(F, 'low_byte((int64_t)base_pitch + scaled(stress, scale));',
                 'low_byte((int64_t)base_pitch + stress);')],
         killed_by=KILLED),
    dict(name='scaled() rounds instead of truncating',
         edits=[(F, '    return (int)v;\n', '    return (int)(v + 0.5);\n')],
         killed_by=KILLED),

    # create_transitions: SAM's ramp and blends.
    dict(name='ramp lifts a 0 too (no `elif val:`)',
         edits=[(F, '            } else if (val != 0) {', '            } else {')],
         killed_by=KILLED),
    dict(name='ramp never corrects the error term',
         edits=[(F, '        error += remainder;\n', '')],
         killed_by=KILLED),
    dict(name='read() wraps negative positions too',
         edits=[(F, '    if (i < 0 || i >= r.n) {\n        return 0;\n    }\n    return r.wide',
                 '    if (i >= r.n) {\n        return 0;\n    }\n    if (i < 0) {\n        i += r.n;\n    }\n    if (i < 0) {\n        return 0;\n    }\n    return r.wide')],
         killed_by=KILLED),
    dict(name='bit 7 test on 0x40',
         edits=[(F, '& 0x80u) != 0', '& 0x40u) != 0')],
         killed_by=KILLED),
    dict(name='equal ranks: in_blend from the in table',
         edits=[(F, '            out_blend = blend(sam_out_blend_length, p);\n            in_blend = blend(sam_out_blend_length, next);',
                 '            out_blend = blend(sam_out_blend_length, p);\n            in_blend = blend(sam_in_blend_length, next);')],
         killed_by=KILLED),
    dict(name='pitch ramp starts at pitch_start ("fixed")',
         edits=[(F, 'interpolate(pitch, cur_width + next_width, trans_start,',
                 'interpolate(pitch, cur_width + next_width, pitch_start,')],
         killed_by=KILLED),
    dict(name='pitch ramp skipped at pitch_start 0',
         edits=[(F, 'if (pitch_end < n && pitch_start >= 0) {', 'if (pitch_end < n && pitch_start > 0) {')],
         killed_by=KILLED),

    # prepare_frames: the F1 adjustment and the amplitude rescale.
    dict(name='F1 adjustment uses a quarter, not a half',
         edits=[(F, 'scaled(fr->freq[0][i] >> 1, scale);', 'scaled(fr->freq[0][i] >> 2, scale);')],
         killed_by=KILLED),
    dict(name='F1 adjustment in sing mode too',
         edits=[(F, '    if (!voice->singmode) {\n        /* Take half', '    if (1) {\n        /* Take half')],
         killed_by=KILLED),
    dict(name='amplitude 16 and up rescaled too (& 15)',
         edits=[(F, '            if (a < SAM_AMPLITUDE_LEVELS) {\n                fr->ampl[f][i] = sam_amplitude_rescale[a];',
                 '            {\n                fr->ampl[f][i] = sam_amplitude_rescale[a & 15];')],
         killed_by=KILLED),

    # Q1: the pitch row. A byte is not enough; int16_t holds the corpus
    # (largest 658) but is not proved, so it lives here and is not used.
    dict(name='Q1: pitch row a byte',
         edits=[(Q, 'typedef int32_t sam_pitch_t;', 'typedef uint8_t sam_pitch_t;')],
         killed_by=KILLED),
    dict(name='Q1: pitch row int16_t (holds the corpus)',
         edits=[(Q, 'typedef int32_t sam_pitch_t;', 'typedef int16_t sam_pitch_t;')],
         killed_by=LIVES),

    # Q2: negative indexing, "fixed" on either side.
    dict(name='Q2: rewrite skips negative writes',
         edits=[(Q, '    return (i + n >= 0) ? i + n : -1;', '    return -1;')],
         killed_by=KILLED),
    dict(name='Q2: oracle skips negative writes',
         edits=[(PY, '            if frame < len(tables[table]):',
                 '            if 0 <= frame < len(tables[table]):')],
         killed_by=KILLED),

    # The dropped idioms, removed from the oracle: no input reaches them.
    dict(name='oracle: int(change / width) as integer division (equivalent)',
         edits=[(PY, '        div = int(change / width)',
                 '        div = -(-change // width) if sign else change // width')],
         killed_by=LIVES),
    dict(name='oracle: no negative amplitude index (equivalent)',
         edits=[(PY, '        if amplitude[0][i] < len(AMPLITUDE_RESCALE):',
                 '        if 0 <= amplitude[0][i] < len(AMPLITUDE_RESCALE):'),
                (PY, '        if amplitude[1][i] < len(AMPLITUDE_RESCALE):',
                 '        if 0 <= amplitude[1][i] < len(AMPLITUDE_RESCALE):'),
                (PY, '        if amplitude[2][i] < len(AMPLITUDE_RESCALE):',
                 '        if 0 <= amplitude[2][i] < len(AMPLITUDE_RESCALE):')],
         killed_by=LIVES),
    dict(name='oracle: F1 halved by truncation, not floor (equivalent)',
         edits=[(PY, 'f1_adjust = int((frequency[0][i] >> 1) * scale)',
                 'f1_adjust = int(int(frequency[0][i] / 2) * scale)')],
         killed_by=LIVES),
    dict(name='oracle: formant and amplitude rows masked to a byte (equivalent)',
         edits=[(PY, '            if frame < len(tables[table]):\n                tables[table][frame] = val',
                 '            if frame < len(tables[table]):\n                tables[table][frame] = val if table == 0 else val & 0xFF')],
         killed_by=LIVES),

    # The dump tool lying.
    dict(name='dump: frame count off by one',
         edits=[(D, 'printf("%d %d %lu", t, fr.count,', 'printf("%d %d %lu", t, fr.count + 1,')],
         killed_by=KILLED),
    dict(name='dump: pitch hashed as a byte',
         edits=[(D, 'h = fnv_int(h, row[i]);\n    }\n    return h;\n}\n\nstatic uint32_t hash_bytes',
                 'h = fnv_int(h, (uint8_t)row[i]);\n    }\n    return h;\n}\n\nstatic uint32_t hash_bytes')],
         killed_by=KILLED),
    dict(name='dump: amplitude rows in the wrong order',
         edits=[(D, 'hash_bytes(fr.ampl[r], fr.count)', 'hash_bytes(fr.ampl[2 - r], fr.count)')],
         killed_by=KILLED),
]
