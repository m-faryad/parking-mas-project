# Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Agent framework | Custom lightweight event-driven Python | Needs exact capacity invariants, paired seeds and event-level logs; avoids a heavy dependency. Mesa (Kazil et al., 2020) is a valid alternative – not used. |
| Time | Discrete-event, minutes | Efficient; exact occupancy integration |
| UI | Streamlit | Local browser dashboard, no account/API key; `st.fragment(run_every)` gives real play/pause |
| Charts | matplotlib (saved + UI) and plotly (live occupancy) | Static files for reports; interactive live view |
| Colour | Okabe-Ito blue/vermilion + marker/line/hatch differences | Not colour-only (WCAG 1.4.1) |
| Storage | CSV + JSON | Readable, diff-able |
| Tests | pytest + Streamlit AppTest | Includes UI smoke tests |
| Strategies | First-available vs weighted-cost | Transparent baseline vs documented multi-criteria rule |
| Distances | Explicit per-space drive/walk model | Needed for any distance or emission claim |
| Candidate reduction | first free per type | Dominance argument; verified against brute force |
