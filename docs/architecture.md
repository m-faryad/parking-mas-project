# Architecture

```
datagen ──► Simulation (engine) ──► metrics ──► experiment ──► analytics ──► figures/tables
 (synthetic)   │  event heap, clock        (runs.csv ...)               ▲
               ▼                                                         │
   ManagementAgent ─ strategy.rank()      Streamlit app (app/) reads the same modules/files
     │ query/offer      │
CarParkAgent ─► ParkingSpaceAgent        VehicleAgent (accepts/declines offers)
```

## Agents (src/parking_mas/model.py)
| Agent | State | Behaviour |
|---|---|---|
| VehicleAgent | type (standard/ev/accessible), arrival, duration, patience, walk limit, lifecycle state, history | Evaluates an offer: accepts iff the space is eligible and its walk distance is within its limit |
| ParkingSpaceAgent | type, index, drive/walk distance, occupant, history | Owns occupancy; raises `AllocationError` on double occupy, wrong-vehicle or double release |
| CarParkAgent | its spaces, sorted free-lists per type, occupancy counter | Answers availability queries (first free space of each eligible type), executes allocate/release |
| ManagementAgent | active allocations, strategy, message bus | Receives requests, queries all car parks, ranks candidates, offers in rank order, enforces invariants |

## Communication
Explicit `Message` objects through a `MessageBus` that counts and stores them:
`request → availability_query → availability_reply → offer → accept | decline → release`.
This is **centralised** request/offer negotiation with one manager. It is not a decentralised, market-based or learning protocol.

## Lifecycle (engine.py)
1. Build car parks/spaces from config. 2. Generate (or load) arrivals for the seed. 3. Schedule arrival and sample events.
4. Pop events in time order (departure < abandonment < arrival < sample at equal time).
5. Arrival: validate → manager request → allocate, or queue (patience>0) / fail (patience=0).
6. Departure: release exact space, retry the waiting queue FIFO. 7. Abandonment after patience expires.
8. Integrate occupancy exactly (step function) for utilisation. 9. At horizon check invariants. 10. Save logs/metrics.

**Simulated vs real time.** The clock is in simulated minutes and jumps between events. Wall-clock is used only for `compute_us` (decision computation time), which is non-deterministic and kept separate.

## Invariants enforced (and tested)
One occupant per space; occupied space cannot be re-allocated; occupancy ≤ capacity; one active allocation per vehicle; only eligible free spaces assigned; departure frees the correct space; failed requests leave occupancy unchanged; invalid configuration raises `ConfigError`; same config+seed gives identical results (except wall-clock columns).
