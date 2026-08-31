# Implementation Plan — `system-monitor` (Quickshell widget for KDE Plasma)

> **Status: implemented (M0–M4).** The widget matches `mock/mockup.png` and runs as a
> systemd user service. Deviations from this plan are documented in §9.

Target environment (verified on this machine):

| Fact | Value |
|---|---|
| Desktop | KDE Plasma, Wayland (KWin) |
| Quickshell | 0.3.0 (`/usr/bin/quickshell`), installed via Arch package |
| Kernel | 6.12.104-1-MANJARO |
| GPU | NVIDIA RTX 3060 (`nvidia-smi` available, per-process VRAM query works) |
| zram | `/dev/zram0`, priority 100, world-readable `mm_stat`/`stat`/`io_stat` |
| Disk swap | `/home/swapfile` (32 GB, priority 10) |
| zswap | disabled (`/proc/meminfo` → `Zswapped: 0 kB`) |
| zram writeback | not configured (`backing_dev: none`) |

---

## 1. Problem statement

Existing system monitors (plasma-systemmonitor, btop, conky, KDE widgets) report a single
combined "swap used" number that mixes:

- **zram compaction** (anonymous pages compressed in RAM — cheap, desirable, *not* disk I/O), and
- **real disk swap** (pages written to `/home/swapfile` — slow, usually signals memory pressure).

This conflates healthy zram compaction with harmful disk swapping and leads to wrong
workload/optimization decisions. Additionally:

- RAM "used" shown by most tools doesn't distinguish reclaimable cache, so the number looks scarier than reality.
- No mainstream monitor lists **top VRAM consumers per process** (critical when local LLMs share the GPU with desktop apps).

## 2. Product scope

A **single floating desktop widget** (not a bar, not a panel, not a shell replacement) that shows:

1. **RAM used / available** with an honest breakdown (used, available, cache/reclaimable, SwapCached).
2. **zram stats**: logical data stored, compressed size, compression ratio, actual RAM consumed, savings.
3. **Real disk swap stats**: per-device size/used, *net rate of change* per device (is anything actually being written to the NVMe?), plus system-wide swap-in/out throughput attributed to zram vs disk.
4. **Top VRAM consumers**: total VRAM used + top N processes by GPU memory with process names.

**Explicitly out of scope (for now):** CPU/network graphs, theming beyond a sane dark card look,
audio, battery, per-core stats, replacing any Plasma component.

**Safety contract (non-negotiable):**

- Run as an *ordinary user process alongside* `plasmashell`. Never replace it, never disable it.
- **Read-only**: only read `/proc`, `/sys`, and run read-only CLI queries (`nvidia-smi` query flags). Never write to `/sys` (no `reset`, `compact`, `mem_limit`, no zram reconfiguration).
- **No root required.** If a data source is unreadable, degrade gracefully to "n/a" with a visible note — never block, never crash, never spawn sudo prompts.
- Bounded polling: total widget CPU budget ~<1% idle; all timers pausable; full kill switch = stop the service.

## 3. Architecture

```
shell/
├── shell.qml                # ShellRoot: instantiates the single MonitorWindow
├── Config.qml               # user-tunable constants (intervals, thresholds, toggles)
├── service/
│   ├── MemInfo.qml          # /proc/meminfo  → RAM + SwapCached + zswap fields
│   ├── Zram.qml             # /sys/block/zram0/{mm_stat,stat,io_stat} + /proc/swaps zram row
│   ├── SwapDisk.qml         # /proc/swaps (disk rows) + /proc/vmstat rates + attribution
│   ├── Vram.qml             # nvidia-smi queries (+ fdinfo fallback path for AMD machines)
│   └── SystemSnapshot.qml   # Singleton aggregating all collectors into one reactive state
├── widget/
│   ├── MonitorWindow.qml    # FloatingWindow, drag handling, persistence
│   ├── RamCard.qml
│   ├── ZramCard.qml
│   ├── SwapCard.qml
│   ├── VramCard.qml
│   └── lib/Format.qml       # bytes/kB→human readable, rates, pct bars
└── assets/                  # icons if needed
```

Design principles:

- **Every collector is a `Singleton` QML file** exposing read-only properties (`ram`, `zram`, `swap`, `vram` objects). UI never touches `/proc` directly — only the snapshot state.
- Parsing lives next to the source it parses (`Zram.qml` knows `mm_stat` field layout).
- UI is dumb: renders the snapshot state, no I/O.
- Config is a single QML singleton so intervals/limits can be tuned in one place.

## 4. Data sources & formulas (the hard part — done carefully)

### 4.1 RAM (`service/MemInfo.qml`)

Source: `/proc/meminfo` (kB fields). Poll every **1 s** via `Timer` + `FileView.reload()`
(**not** `watchChanges` — procfs doesn't fire inotify reliably).

Derived properties:

- `used` = `MemTotal - MemAvailable` (KDE-convention "true usage")
- `available` = `MemAvailable`
- `cacheReclaimable` = `Cached + SReclaimable - Shmem`
- `swapCached` = `SwapCached` (pages that left RAM but still have a swap copy — relevant to swap-in cost)
- `zswapUsed` = `Zswap`, `zswapCompressed` = `Zswapped` (0 here, but read them so the widget stays correct if zswap is ever enabled)

### 4.2 zram (`service/Zram.qml`)

Sources:

- `/sys/block/zram0/mm_stat` — fields (verified present on this kernel):
  `orig_data_size, compr_data_size, mem_used_total, mem_limit, mem_used_max, same_pages, huge_pages, huge_pages_failed, huge_pages_alloc` (tolerate both 6-field old and 9-field new layouts).
- `/proc/swaps` row where filename starts with `/dev/zram` — authoritative *swap-side* usage (`Used` kB).
- `/sys/block/zram0/stat` (diskstat layout) and `io_stat` — for I/O-rate deltas.

Derived:

- `logicalStored` = mm_stat[0]
- `compressed` = mm_stat[1]
- `ramHeld` = mm_stat[2] (`mem_used_total` — actual RAM consumed holding zram)
- `compressionRatio` = logicalStored / compressed
- `ramSaved` = logicalStored − ramHeld
- `hugePages` counts (regression signal when ratio degrades)

### 4.3 Disk swap + attribution (`service/SwapDisk.qml`) — the core fix

Sources:

- `/proc/swaps`: **split rows into `zram` devices vs `disk` devices** (filename prefix `/dev/zram`).
  Each area: size, used, priority.
- `/proc/vmstat`: `pswpin`, `pswpout` (cumulative, pages; **includes zram traffic**), `zswpin/zswpout` (zswap, 0 here).
- zram I/O: `/sys/block/zram0/stat` write/read sectors (4 KiB zram sectors) deltas.

Rate attribution per sampling window (default 2 s):

```
swapOutTotalPagesΔ  = pswpout_now - pswpout_prev
zramWritePagesΔ     = (zram stat write_sectorsΔ) / 8   // 8 sectors per 4 KiB page
diskSwapOutPagesΔ   = max(0, swapOutTotalPagesΔ - zramWritePagesΔ)
```

Plus a **net-balance view per device** (authoritative, immune to attribution edge cases):

```
zramUsedΔ  = /proc/swaps zram row UsedΔ      → positive: compaction happening
diskUsedΔ  = /proc/swaps disk rows UsedΔ     → positive: REAL disk swap happening
```

UI verdict states (this is what the user actually needs):

- `zram-only`: zram Used rising, disk Used flat → "compacting in RAM ✔"
- `disk-pressure`: disk Used rising or `diskSwapOut` rate > 0 → "REAL disk swap ✖ kB/s"
- `draining`: values shrinking → "swap being read back"
- `idle`: nothing changing

### 4.4 VRAM consumers (`service/Vram.qml`)

Primary (NVIDIA, this machine): `Process.exec` of two read-only queries every **5 s**:

- `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits`
- `nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader,nounits`
  → for each pid: read `/proc/<pid>/comm` to get the short friendly name; **validate pid is alive and comm matches the reported basename** (guards against PID reuse races; drop stale entries instead of mislabeling).

Fallback paths (keep for AMD/other machines / future portability):

- Generic: scan `/proc/*/fdinfo/*` for `drm-` fields (`vram`, `gtt`, `dma-buf`) — works with amdgpu fdinfo.
- Graceful degrade when `nvidia-smi` missing: hide card, log once.

Nuance shown in UI: per-process sum ≠ GPU total (driver-reserved + graphics overhead) — show total separately, never fake a "sum" as total.

## 5. UI & interaction

### 5.1 Window model

- `FloatingWindow` — a normal toplevel window. Works on KWin/Wayland today, movable anywhere, drag across monitors. Chosen over `PanelWindow` because the requirement is a **free-floating widget**, not an edge-anchored panel.
- Frameless content card, small **drag strip** (grip handle) at the top: `MouseArea`/`DragHandler` that updates `window.x/y` while dragging, clamped to the current screen bounds.
- Multi-screen: position clamped against `Quickshell.screens`; window keeps its screen assignment.

### 5.2 Placement persistence

- `PersistentProperties` stores `x`, `y`, `collapsed`, compact mode, interval overrides → survives reloads (and live-edit iteration), stored in Quickshell's state dir.
- Optional helper: a KWin window-rule note in docs ("keep below others", "no focus stealing") so the widget feels like desktop furniture without us fighting the compositor.

### 5.3 Layout

Vertical compact card stack (auto-width ~360 px):

```
┌ RAM ─────────────────────────────┐
│ ▕██████████░░░░░▏  18.2 / 31.3 GB │
│ available 24.9 GB · cache 1.4 GB │
├ zram ────────────────────────────┤
│ 6.1 GB logical → 1.6 GB (3.9:1)  │
│ RAM held 1.7 GB · saved 4.4 GB   │
│ compaction ▲ 12 MB/s (in RAM ✔)  │
├ Disk swap ───────────────────────┤
│ /home/swapfile 185 MB of 32 GB   │
│ disk swap-out: 0 kB/s (idle ✔)   │
├ VRAM ────────────────────────────┤
│ 11.2 / 12.3 GB                   │
│ opencode_beta   4516 MB          │
│ llama-cli       3564 MB          │
│ llama-cli       2478 MB          │
└──────────────────────────────────┘
```

- One-line-per-metric, no graphs in v1 (rates as text arrows ▲▼ + color: green=compaction/idle, amber=slow drain, red=real disk swap-out).
- Click on any header collapses/expands that card; double-click grip hides to a small pill ("R18 z6 D0 V11.2") with tooltip — minimal desktop footprint mode.

## 6. Precautions ("do not break things")

1. **No shell takeover**: launch as `quickshell -p <config path>` in a systemd *user* service; `plasmashell` untouched. Kill switch: `systemctl --user stop qs-system-monitor`.
2. **Read-only I/O only.** A grep-guarded review rule in AGENTS.md: `Process.exec` commands must be from an allowlist (`nvidia-smi --query-*`, `pgrep`). No writes outside our own state file.
3. **Never block the render loop.** All reads async (`FileView` async load, `Process` non-blocking); parse failures produce `n/a`, not exceptions.
4. **Poll budget**: 1 s meminfo (tiny file), 2 s swap/zram (tiny files), 5 s `nvidia-smi` (subprocess spawn; use one combined query per tick). Timers stop when window `visible: false`.
5. **Permission degradation**: if `mm_stat` unreadable (some setups restrict it), still show `/proc/swaps` zram Used with an "advanced stats unavailable" note. Never retry-storm.
6. **Process races**: VRAM pid list re-validated against `/proc/<pid>/comm` every tick; dead pids dropped.
7. **Layout edge cases**: mm_stat field-count variations; missing zram device (`/sys/block/zram*` glob empty → zram card renders "no zram configured"); multiple swap files (list each).
8. **Reload safety**: all mutable state behind Singletons + `PersistentProperties`; quickshell live-reload must not duplicate timers (idempotent collectors).
9. **Memory of the monitor itself**: keep snapshots tiny (no history buffers > a few samples in v1; no graphs yet).

## 7. Milestones

### M0 — Skeleton boots (no data)
- `shell.qml` + `MonitorWindow.qml` floating card renders; drag strip moves it; position persists across reload.
- systemd user unit installs; widget appears after login; `systemctl --user stop` kills it cleanly; Plasma unaffected.
- **Accept:** drag to any position → reload quickshell → position retained; `journalctl --user -u qs-system-monitor` clean.

### M1 — RAM + zram cards
- MemInfo + Zram collectors with the formulas above; cards render live values that match `free -h` and `zramctl` outputs within rounding.
- **Accept:** `used` ≈ KDE convention; compression ratio matches `zramctl`'s ALGO/RATIO; unit tests via a tiny `qs` console check script (documented in AGENTS.md).

### M2 — Disk swap + attribution (the flagship feature)
- SwapDisk collector with per-device Used deltas + vmstat/zram attribution; verdict states drive card color.
- **Accept:** while running only a browser + editor, card shows `zram-only / idle`; stress test (`stress-ng --vm`) or an intentional `chrt` memory hog shows `disk-pressure` only when the NVMe is truly being written (verify against `/proc/diskstats` manually once).

### M3 — VRAM card
- nvidia-smi queries + pid validation + top-N list; graceful hide on missing binary.
- **Accept:** launching/stopping a CUDA process updates the list within one tick; desktop apps (kwin, brave gpu-proc) appear with friendly names.

### M4 — Polish
- Collapse/pill modes, Config.qml knobs (intervals, thresholds, top-N), docs, screenshot, final README/AGENTS alignment.

## 8. Risks

| Risk | Mitigation |
|---|---|
| KWin Wayland restricts arbitrary positioning | Positioning generally honored for toplevels on KWin; if a future compositor forbids it, fall back to `PanelWindow` edge anchoring mode (kept as a config flag). |
| `nvidia-smi` spawn cost every 5 s | Single combined query; increase interval in Config; consider caching and only re-spawning when card visible. |
| vmstat attribution edge cases (e.g., future zram writeback) | `backing_dev` is read and, if non-`none`, attribution switches to `bd_stat` deltas; net-balance per-device view stays authoritative. |
| Driver/kernel updates change file layouts | Parsers tolerate field-count drift; unknown fields ignored; missing → n/a. |
| Quickshell API drift (0.3.x) | Pin docs to installed version; smoke-run on every update (scripted check in AGENTS.md). |

## 9. Implementation notes & deviations (post-implementation record)

### 9.1 Window model: PanelWindow (layer-shell), not FloatingWindow

The mockup nominally says "FloatingWindow", but on Wayland a FloatingWindow:

- cannot be programmatically positioned (no x/y API), so **position persistence is impossible**;
- always floats above application windows and participates in focus — fighting the "desktop
  furniture" requirement.

The widget is therefore a `PanelWindow` (wlr layer-shell) with **left+top anchors and
margin-based position**:

- drag updates the persisted margins (`PersistentProperties`: posX/posY/pinned/collapsed);
- unpinned it lives **below** application windows (true desktop widget); the pin (📌) button
  toggles `aboveWindows` (top layer) — exactly what the mockup's pin means;
- `exclusionMode: Ignore` so it never reserves screen space;
- `focusable: false` so it never steals keyboard focus.

### 9.2 Scope additions from the mockup

The mockup added three things that were "out of scope" in §2. They are implemented:

- **Top strip** with CPU (busy% + avg MHz), RAM, Swap, GPU VRAM ring gauges and a disk **I/O**
  block (sparkline + R/W rates) — `service/Cpu.qml`, `service/DiskIo.qml` (`/proc/stat`,
  `/proc/cpuinfo`, `/proc/diskstats` whole disks only);
- **Header controls**: minimize (collapse to pill), pin (aboveWindows), close (quits the
  instance — equivalent to the systemd kill switch);
- **Footer chips** mirroring the safety posture.

### 9.3 Quickshell 0.3.0 API gotchas (keep for future work)

- `FileView.text` is a **function** in the public wrapper (`text()`), not a property; the
  `onTextChanged` signal still fires on (re)load. Calling `text()` inside the handler is required.
- Quickshell `Singleton`s are **lazily instantiated** on first reference. Collectors are only
  instantiated early because the UI binds to them at startup. Test harnesses must reference
  them via a binding (see the `Item` at the top of `shell/collector-check.qml`).
- `PersistentProperties` persists properties declared *inside it* across reloads and restarts.
- Quickshell forbids imports escaping the config root (`../..` from `shell/`), which is why
  the collector check harness lives at `shell/collector-check.qml`.
- Signal parameter injection (`onExited: exitCode => ...`) is deprecated; use arrow functions
  with formal parameters.
- Never mutate persisted window state from a pointer **release** handler: the write-back can
  race the drag that just finished (observed as "the widget only drags once"). Same-screen
  drops leave the drag's position untouched; only cross-screen hand-offs rewrite state.
- Do not destroy and recreate a `PanelWindow` during a cross-screen hand-off. On this Qt/KWin
  stack that can invalidate the shared scenegraph context and leave the replacement unable to
  drag. Cache one surface per visited output and switch their visibility after pointer release.
- Coalesce raw pointer motion to at most one layer-shell margin update per frame. Every margin
  change requires a compositor reconfigure; applying every mouse event makes dragging visibly
  redraw in small, laggy steps.

### 9.4 Verification performed (2026-08-31)

- `scripts/parse-test.mjs` — 22 assertions against live `/proc`, `/sys` and synthetic
  nvidia-smi output: all pass.
- `shell/collector-check.qml` — live values match `free -h`, `/proc/swaps`, `mm_stat` ratio
  (3.6x ≈ `zramctl`), and a live GPU process appeared correctly with a friendly name.
- systemd service boots, journal clean, steady state ~1.6% CPU / 0.6% memory (300 MB RSS
  including Qt runtime).
