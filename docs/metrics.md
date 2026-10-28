# Metrics

Observation window: simulated minutes [0, `duration_min`]. *Valid request* = request with valid fields arriving in the window.
Every valid request ends the window as exactly one of **served / failed / pending**.

| Metric (column) | Definition | Unit |
|---|---|---|
| `success_rate` | served ÷ valid requests (served = allocated a space at any time in the window, including after waiting) | share |
| `failed_rate` | failed ÷ valid (`no_wait`: could not park and had no patience; `timeout_full`/`timeout_declined`: patience expired) | share |
| `pending_rate` | still waiting at window end ÷ valid | share |
| `utilisation` | ∫ occupied spaces dt ÷ (total capacity × window), computed exactly from the step function (per car park: `util_<name>`) | share of space-minutes |
| `peak_occupancy_ratio`, occupancy time series | occupied ÷ capacity sampled every `sample_interval_min` | share |
| `mean_wait_min`, `p95_wait_min` | allocation time − request time over **served** requests (simulated minutes; 0 if parked immediately) | min |
| `mean_queue_length` | mean of sampled queue length | vehicles |
| `mean_decision_ms` | wall-clock time of the manager's decision (**real** computation time; non-deterministic) | ms |
| `alloc_<cp>`, `alloc_share_<cp>` | served vehicles per car park and their share | count / share |
| `mean_drive_m`, `mean_walk_m`, `total_drive_km` | from the modelled distances of served vehicles | m / km |
| `ev_bay_match_rate` | served EVs in EV bays ÷ served EVs (NaN if no EV served) | share |
| `co2e_proxy_kg` | (`total_drive_km` × `emission_g_per_km` + `total_wait_min` × `idle_g_per_min`) ÷ 1000 | kg CO2e, **simulation estimate** |

## Emission proxy – assumptions and limits
* Counts only the modelled in-park drive distance of served vehicles and idle waiting time of every valid request.
* Factors (150 g/km, 20 g/min) are **illustrative defaults, not sourced measurements**; change them in the scenario.
* Excludes walking, trips before the campus gate, cruising between car parks, vehicle mix, cold-start effects, upstream emissions.
* It is **not** measured environmental impact. Higher utilisation is not treated as an environmental benefit.
* Because the coordinated strategy shortens walking but lengthens driving, the proxy can rise even while user walking falls – see results.
