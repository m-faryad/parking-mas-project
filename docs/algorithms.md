# Allocation strategies

Candidates: each car park agent returns the **lowest-index free space of every eligible type**. Within a type, drive and walk distance both grow with the index, so any cost that is non-decreasing in distance is minimised by that first free space. A unit test compares the coordinated choice to a brute-force minimum over all free spaces.

## Eligibility
standard vehicle → standard bays only; EV → EV or standard bays; accessible permit → accessible or standard bays. Reserved bays are never given to vehicles without the matching need.

## Layout / distances (explicit model)
Space `i` in car park `c`: `drive_m = gate_distance_m + i*pitch_m`, `walk_m = walk_base_m + i*pitch_m`.
Layout order along the aisle: accessible (nearest), standard, EV bays (rear). Distances are synthetic modelling choices.

## Strategy A – Baseline (first available)
```
rank(v, candidates): sort by (car-park order in config, space index)
```
Ignores distance, congestion and reserved-bay preservation. Complexity O(#car parks). Weakness: fills early car parks first, regardless of walking distance; EVs get standard bays near the front rather than EV bays.

## Strategy B – Coordinated (weighted cost)
```
cost(v, c) = w_drive*drive_m + w_walk*walk_m*(3 if v accessible else 1)
           + w_congestion*occupancy_ratio(car park)
           - ev_bonus*[v is EV and bay is EV] - accessible_bonus*[v accessible and bay accessible]
rank(v, candidates): sort ascending by (cost, car-park order, index)
```
Default weights (metre-equivalents): w_drive 1, w_walk 1.5, w_congestion 300, ev_bonus 400, accessible_bonus 400. These are **modelling choices, not tuned or calibrated**; w_walk > w_drive makes the strategy trade driving for walking.
Complexity O(#car parks × types) per request.

## Offer protocol (both strategies)
Manager offers candidates in rank order; the vehicle declines when walk distance exceeds its own limit; if all are declined or none exist the vehicle waits (patience > 0) or leaves. Waiting vehicles are retried FIFO whenever a space is released.

## Known weaknesses
Greedy and myopic (no look-ahead on future arrivals or durations); cost weights are arbitrary; no driver cruising or information asymmetry; centralised manager is a single point of failure in the model.
