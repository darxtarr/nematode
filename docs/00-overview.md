# Overview

Reflex is a sandbox for **KML-style reflexes** — small deterministic models that adapt runtime policies locally.

It isolates the reflex concept from larger projects like *Chorus* so that we can iterate quickly and test boundaries.

### Architecture
1. **Telemetry collector** – samples low-cost metrics at 100 ms–1 s intervals.
2. **Offline trainer** – fits small models (tree / regressor / quantized NN).
3. **Reflex file (.reflex)** – serialized weights + metadata.
4. **Runtime loader** – executes inference loop and applies decisions.
5. **Evaluator** – compares performance against baseline heuristics.

### Design Principles
- Deterministic runtime, no allocations.
- Reflex ≈ < 1 µs per inference.
- Models < 10 KB.
- Offline retraining and hot-swap.
- Transparent rollback + provenance tracking.

### Biological Analogy
Each reflex = a **ganglion**, executing simple local control loops.  
Global coordination emerges from fleet behavior, not central planning.
