# `.reflex` File Format

Binary, self-describing container for trained reflex models.

## Layout
| Section | Description |
|----------|-------------|
| Header | magic `NEM1`, version, feature_hash, created_at |
| Model | type, quantization, weight array |
| Bounds | min/max for outputs |
| Metadata | trainer_commit, telemetry_hash |
| Checksum | CRC32 |

## Safety
- Read-only mapped at runtime.
- No dynamic allocation.
- Output values clamped to safe ranges.
- Baseline heuristic always available as fallback.

## Example Metadata
created_at: 2025-10-06T11:45Z
trainer: "Sonny 4.5"
feature_schema: "telemetry-v1"
trainer_commit: "af1c3b2"
notes: "trained on workload set A-burst"