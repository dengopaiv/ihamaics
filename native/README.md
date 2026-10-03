# native/ — the C port, frozen as reference

**Frozen on 2026-10-03.** This is the C port of SAM that ships today. It is
byte-identical to the Python engine in `nvda-addon/synthDrivers/sam/` over
every domain the verifiers in `tools/` cover. It is now the reference that
the C17 rewrite in `../engine/` is checked against, next to the Python.
The plan is [`docs/c17-rewrite-plan.md`](../docs/c17-rewrite-plan.md).

What frozen means here:

- **`src/` and `include/` do not change**, except for a bug found in
  them. That bug is then fixed here and in the rewrite, with the reason
  logged in the plan. Nothing here is tidied, modernised or moved to C17.
  It already compiles as strict C17 (plan §1), and changing it has no
  purpose.
- **`tools/` is shared.** The verifiers check either implementation:
  `--impl native` (the default) or `--impl engine`. See `tools/_build.py`.
  They change as the stages need, and they move to the top-level `tools/`
  before this directory leaves `master` (plan §3.1, stage R.11).
- **`tests/golden/` is shared** too, and is regenerated only when the
  Python renderer changes on purpose.

When the rewrite has replaced this engine, `native/` moves to a branch
of its own. It stays buildable there; `master` then carries the rewrite.

How this engine was built and verified:
[`docs/c-engine-port.md`](../docs/c-engine-port.md) (the renderer) and
[`docs/native-gui.md`](../docs/native-gui.md) (the front end and the GUI).

Build:

    native\build.cmd                    :: sam_render-x64.dll
    python native\tools\gen_dict.py     :: native\data\sam.dict
