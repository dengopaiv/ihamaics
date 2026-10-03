"""Stage R.1 mutants: the renderer tables (docs/c17/01-r1-tables.md).

Run with: python engine/tools/mutate.py r1

Two checks guard the tables, and they see different things:

  verify_tables   the values the compiled engine holds, through
                  engine/tools/dump_tables.c, against renderer_tables.py;
  tables_current  the generated files' text, against what
                  engine/tools/gen_tables.py would write now.

Each mutant is one edit, and killed_by names the checks that must fail.
Paths are relative to the repository root; anchors are matched with
LF line endings and must occur exactly once.
"""

CHECKS = {
    'verify_tables': ['native/tools/verify_tables.py', '--impl', 'engine'],
    'tables_current': ['engine/tools/gen_tables.py', '--check'],
}

T = 'engine/src/tables.c'
H = 'engine/src/tables.h'
D = 'engine/tools/dump_tables.c'
PY = 'nvda-addon/synthDrivers/sam/renderer_tables.py'

BOTH = ('verify_tables', 'tables_current')

MUTANTS = [
    # A generated table edited by hand: the case the generator exists for.
    dict(name='freq1[0] 0 -> 1',
         edits=[(T, 'sam_freq1[SAM_PHONEME_COUNT] = {\n       0,',
                 'sam_freq1[SAM_PHONEME_COUNT] = {\n       1,')],
         killed_by=BOTH),
    dict(name='ampl3[79] 16 -> 17 (last entry)',
         edits=[(T, '0,   19,   16\n};', '0,   19,   17\n};')],
         killed_by=BOTH),
    dict(name='out_blend_length[79] 160 -> 161 (last entry)',
         edits=[(T, '2,  160,  160\n};', '2,  160,  161\n};')],
         killed_by=BOTH),
    dict(name='sample_table[1279] 252 -> 253 (last byte)',
         edits=[(T, '15,    0,  252\n};', '15,    0,  253\n};')],
         killed_by=BOTH),
    dict(name='sinus[1] 3 -> 4',
         edits=[(T, 'sam_sinus[SAM_SINUS_SIZE] = {\n       0,    3,',
                 'sam_sinus[SAM_SINUS_SIZE] = {\n       0,    4,')],
         killed_by=BOTH),
    dict(name='sinus[255] -3 -> 3 (sign)',
         edits=[(T, '-6,   -3\n};', '-6,    3\n};')],
         killed_by=BOTH),
    dict(name='stress_pitch[1] 224 -> 225',
         edits=[(T, '       0,  224,  230,', '       0,  225,  230,')],
         killed_by=BOTH),
    dict(name='amplitude_rescale[15] 15 -> 14',
         edits=[(T, '11,   13,   15\n};', '11,   13,   14\n};')],
         killed_by=BOTH),
    dict(name='sampled_consonant_values0[0] 24 -> 25',
         edits=[(T, '      24,   26,   23,   23,   23\n};',
                 '      25,   26,   23,   23,   23\n};')],
         killed_by=BOTH),
    dict(name='time_table[4][4] 54 -> 55 (last cell)',
         edits=[(T, '{  199,    0,    0,   54,   54 }',
                 '{  199,    0,    0,   54,   55 }')],
         killed_by=BOTH),

    # The oracle changed and nobody regenerated: the C now disagrees with
    # the Python (verify_tables) and is stale (tables_current).
    dict(name='Python STRESS_PITCH_TABLE changed, not regenerated',
         edits=[(PY, '0x00, 0xE0, 0xE6,', '0x00, 0xE1, 0xE6,')],
         killed_by=BOTH),

    # Text the compiled values do not show: only the generator sees it.
    dict(name='tables.h comment edited by hand',
         edits=[(H, 'Byte 2 of\n * FREQUENCY_DATA.', 'Byte 2 of\n * FREQUENCY_DATA!')],
         killed_by=('tables_current',)),

    # The dump tool lying: only the value verifier sees it.
    dict(name='dump prints freq2 under the name freq1',
         edits=[(D, '    DUMP_U8(sam_freq1);',
                 '    dump_u8("sam_freq1", sam_freq2, SAM_PHONEME_COUNT);')],
         killed_by=('verify_tables',)),
    dict(name='dump prints sinus as unsigned',
         edits=[(D, '    DUMP_I8(sam_sinus);',
                 '    dump_u8("sam_sinus", (const uint8_t *)sam_sinus, SAM_SINUS_SIZE);')],
         killed_by=('verify_tables',)),
    dict(name='dump drops the last time_table row',
         edits=[(D, 'r < SAM_TIME_TABLE_ROWS;', 'r < SAM_TIME_TABLE_ROWS - 1;')],
         killed_by=('verify_tables',)),
    dict(name='dump omits a table',
         edits=[(D, '    DUMP_U8(sam_blend_rank);\n', '')],
         killed_by=('verify_tables',)),
]
