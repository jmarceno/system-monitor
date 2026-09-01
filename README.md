# System Monitor

A readable, free-floating desktop widget for KDE Plasma on Wayland, built with
[Quickshell](https://quickshell.outfoxxed.me/).

<p align="center">
  <img src="./mock/screenshot.png" alt="System Monitor widget showing memory, swap attribution, zram and NVIDIA VRAM" width="437">
</p>

## What it shows

- RAM used, available memory, cache and memory pressure
- zram compression, RAM held and savings
- Real disk swap usage and write rate, separated from zram activity
- Total NVIDIA VRAM and top GPU-consuming processes
- CPU, RAM, swap, VRAM and disk-I/O summaries at a glance
- An expandable full-height storage sidecar with free space for mounted internal
  and removable devices; it refreshes automatically when media is added or removed

The main idea is simple: zram compaction happens in RAM, while disk swap is
actual storage I/O. They should never be presented as the same kind of pressure.

## Run

```bash
# Install, enable and start the user service
./scripts/install.sh --start

# Or run directly during development (live reload)
quickshell -p ./shell
```

To stop the service:

```bash
systemctl --user stop qs-system-monitor
```

Requires Quickshell 0.3+, KDE Plasma on Wayland and Linux. zram is optional;
the widget degrades gracefully when it is unavailable. NVIDIA VRAM details use
`nvidia-smi` when available.

## Safety

The widget runs alongside Plasma as a normal user process. It only reads system
statistics from `/proc` and `/sys`, plus read-only `nvidia-smi` and `lsblk` queries.
It does not require root, change zram configuration or replace any Plasma component.

## Documentation

- [PLAN.md](./PLAN.md) — architecture, formulas and implementation milestones
- [AGENTS.md](./AGENTS.md) — contributor and safety rules

## License

TBD
