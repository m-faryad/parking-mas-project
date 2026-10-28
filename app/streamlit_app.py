"""Interactive dashboard for the parking multi-agent simulation (Streamlit).

Run from the project root:  streamlit run app/streamlit_app.py
All numbers shown come from the real simulation / saved experiment files.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from parking_mas import analytics  # noqa: E402
from parking_mas.config import (  # noqa: E402
    STRATEGIES,
    ConfigError,
    config_from_dict,
    load_config,
    predefined_scenarios,
)
from parking_mas.engine import Simulation  # noqa: E402
from parking_mas.experiment import run_experiment  # noqa: E402
from parking_mas.metrics import compute_metrics  # noqa: E402

st.set_page_config(page_title="Parking MAS", page_icon="🅿️", layout="wide")

CSS = """
<style>
.block-container{padding-top:1.4rem;max-width:1400px}
.hero{background:linear-gradient(120deg,#0b2a4a,#12508a);color:#fff;padding:18px 24px;border-radius:12px;margin-bottom:14px}
.hero h1{font-size:1.45rem;margin:0 0 4px 0;color:#fff}.hero p{margin:0;opacity:.9;font-size:.92rem}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:600;border:1px solid #0b2a4a;margin-right:6px}
.grid{display:flex;flex-wrap:wrap;gap:2px;margin:6px 0 12px 0}
.sp{width:17px;height:17px;border:1px solid #555;border-radius:3px;font-size:9px;line-height:15px;text-align:center;font-weight:700}
.sp.free{background:#fff;color:#222}.sp.occ{background:#0b2a4a;color:#fff}
.note{font-size:.82rem;color:#555}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

PAGES = ["Overview", "Simulation", "Scenarios", "Inspector", "Analytics", "Experiments", "Methodology"]


# ------------------------------------------------------------------ state
def init_state() -> None:
    ss = st.session_state
    if "cfg" not in ss:
        demo = ROOT / "configs" / "demo_config.json"
        if os.environ.get("PARKING_MAS_DEMO") and demo.exists():  # set by RUN_DEMO.bat
            ss.cfg, ss.scenario_name = load_config(demo), "high_demand"
        else:
            ss.cfg, ss.scenario_name = predefined_scenarios()["moderate_demand"], "moderate_demand"
    ss.setdefault("strategy", "coordinated")
    ss.setdefault("sim", None)
    ss.setdefault("playing", False)
    ss.setdefault("speed", 15)
    ss.setdefault("msg", None)


def flash(kind: str, text: str) -> None:
    st.session_state.msg = (kind, text)


def show_flash() -> None:
    m = st.session_state.get("msg")
    if m:
        {"ok": st.success, "err": st.error, "warn": st.warning}.get(m[0], st.info)(m[1])
        st.session_state.msg = None


def new_sim() -> Simulation | None:
    try:
        sim = Simulation(st.session_state.cfg, st.session_state.strategy)
    except ConfigError as exc:
        flash("err", str(exc))
        return None
    st.session_state.sim = sim
    return sim


def hero() -> None:
    cfg, sim = st.session_state.cfg, st.session_state.sim
    state = "No simulation" if sim is None else ("Finished" if sim.finished else ("Running" if st.session_state.playing else "Paused / ready"))
    st.markdown(
        f"""<div class="hero"><h1>Agent-Based Intelligent Car Parking Management</h1>
        <p>Multi-agent simulation and analytics for sustainability · MSc AI &amp; Data Science · CSC-44120 · <b>synthetic data only</b></p>
        <p style="margin-top:8px"><span class="badge" style="background:#fff;color:#0b2a4a">Scenario: {cfg.name}</span>
        <span class="badge" style="background:#fff;color:#0b2a4a">Strategy: {st.session_state.strategy}</span>
        <span class="badge" style="background:#fff;color:#0b2a4a">Status: {state}</span></p></div>""",
        unsafe_allow_html=True)


# ----------------------------------------------------------------- pages
def occupancy_chart(sim: Simulation) -> go.Figure:
    s = pd.DataFrame(sim.samples)
    fig = go.Figure()
    for cp in sim.car_parks:
        fig.add_trace(go.Scatter(x=s["time"] / 60, y=s[f"occ_{cp.name}"] / cp.capacity * 100, mode="lines",
                                 name=cp.name, line=dict(shape="hv")))
    fig.add_trace(go.Scatter(x=s["time"] / 60, y=s["occupancy_ratio"] * 100, mode="lines", name="All car parks",
                             line=dict(color="black", dash="dash", width=3, shape="hv")))
    fig.update_layout(height=340, margin=dict(l=10, r=10, t=30, b=10), yaxis=dict(title="Occupied (% capacity)", range=[0, 105]),
                      xaxis_title="Simulated time (hours from start)", legend=dict(orientation="h", y=-0.25),
                      title="Occupancy over simulated time")
    return fig


def page_overview() -> None:
    sim, cfg = st.session_state.sim, st.session_state.cfg
    if sim is None:
        st.info("No simulation yet. Open **Simulation** and press **Start**, or **Run to end**. "
                f"Active scenario: **{cfg.name}** · total capacity **{cfg.total_capacity}** spaces.")
        return
    snap = sim.snapshot()
    c = st.columns(6)
    c[0].metric("Total capacity", snap["capacity"])
    c[1].metric("Occupied now", snap["occupied"], f"{snap['occupied'] / snap['capacity']:.0%} full", delta_color="off")
    c[2].metric("Requests so far", snap["requests"])
    c[3].metric("Successful", snap["parked_total"])
    c[4].metric("Failed", snap["failed"])
    c[5].metric("Waiting", snap["waiting"])
    st.plotly_chart(occupancy_chart(sim), width="stretch")
    if sim.finished:
        m = compute_metrics(sim)
        d = st.columns(5)
        d[0].metric("Success rate", f"{m['success_rate']:.1%}")
        d[1].metric("Utilisation", f"{m['utilisation']:.1%}")
        d[2].metric("Mean wait (sim min)", f"{m['mean_wait_min']:.2f}")
        d[3].metric("Mean drive (m)", f"{m['mean_drive_m']:.0f}")
        d[4].metric("CO₂e proxy (kg, estimate)", f"{m['co2e_proxy_kg']:.1f}")
        st.caption("CO₂e proxy is a simulation-based estimate from illustrative factors, not measured environmental impact.")
    st.caption(f"Simulated clock: minute {snap['time']:.0f} of {sim.horizon:.0f}.")


def tick() -> None:
    sim = st.session_state.sim
    if sim is None or sim.finished:
        st.session_state.playing = False
        return
    sim.step(sim.now + st.session_state.speed)
    if sim.finished:
        st.session_state.playing = False


@st.fragment(run_every=1.0)
def live_runner() -> None:
    """Auto-play: advances the real simulation clock once per second while 'playing'."""
    if st.session_state.playing:
        tick()
        sim = st.session_state.sim
        snap = sim.snapshot()
        st.progress(min(1.0, snap["time"] / sim.horizon), text=f"Running… simulated minute {snap['time']:.0f}/{sim.horizon:.0f} "
                    f"· occupied {snap['occupied']}/{snap['capacity']}")
        if sim.finished:
            st.rerun()
    else:
        sim = st.session_state.sim
        if sim is not None:
            st.progress(min(1.0, sim.now / sim.horizon), text=f"{'Finished' if sim.finished else 'Paused'} at simulated minute {sim.now:.0f}/{sim.horizon:.0f}")


def page_simulation() -> None:
    ss = st.session_state
    sim = ss.sim
    st.subheader("Simulation controls")
    st.caption(f"Active: **{ss.cfg.name}**, seed {ss.cfg.seed}, {ss.cfg.duration_min} min, capacity {ss.cfg.total_capacity}. "
               "Change parameters under **Scenarios**.")
    ss.strategy = st.radio("Allocation strategy", STRATEGIES, horizontal=True, index=STRATEGIES.index(ss.strategy),
                           disabled=ss.playing, help="Baseline: first eligible space. Coordinated: weighted-cost choice.")
    ss.speed = st.select_slider("Speed (simulated minutes per second)", [5, 15, 30, 60, 120], value=ss.speed)
    c = st.columns(6)
    started = sim is not None and not sim.finished and sim.now > 0
    if c[0].button("▶ Start", disabled=ss.playing or (sim is not None and started), width="stretch",
                   help="Create a fresh simulation from the active scenario and play."):
        if new_sim():
            ss.playing = True
            st.rerun()
    if c[1].button("⏸ Pause", disabled=not ss.playing, width="stretch"):
        ss.playing = False
        st.rerun()
    if c[2].button("⏵ Resume", disabled=ss.playing or not started, width="stretch"):
        ss.playing = True
        st.rerun()
    if c[3].button("⏭ Step +30 min", disabled=ss.playing or (sim is not None and sim.finished), width="stretch"):
        if sim is None and not new_sim():
            return
        ss.sim.step(ss.sim.now + 30)
        st.rerun()
    if c[4].button("⏩ Run to end", disabled=ss.playing, width="stretch"):
        if new_sim():
            ss.sim.run()
            flash("ok", "Simulation completed.")
            st.rerun()
    if c[5].button("↺ Reset", width="stretch"):
        ss.playing = False
        ss.sim = None
        flash("ok", "Simulation reset.")
        st.rerun()
    show_flash()
    live_runner()
    if ss.sim is not None:
        page_overview()
    else:
        st.info("Press **Start** to play the simulation live, **Step** to advance manually, or **Run to end**.")


def page_scenarios() -> None:
    ss = st.session_state
    st.subheader("Scenario management")
    pre = predefined_scenarios()
    disabled = ss.playing
    col = st.columns([2, 1, 1])
    choice = col[0].selectbox("Predefined scenario", list(pre), index=list(pre).index(ss.scenario_name) if ss.scenario_name in pre else 0,
                              disabled=disabled)
    if col[1].button("Load scenario", disabled=disabled, width="stretch"):
        ss.cfg, ss.scenario_name, ss.sim = dataclasses.replace(pre[choice]), choice, None
        flash("ok", f"Loaded '{choice}'.")
        st.rerun()
    if col[2].button("Reset to defaults", disabled=disabled, width="stretch"):
        ss.cfg, ss.scenario_name, ss.sim = dataclasses.replace(pre["moderate_demand"]), "moderate_demand", None
        flash("ok", "Reset to defaults.")
        st.rerun()
    show_flash()
    cfg = ss.cfg
    st.caption(cfg.description)
    with st.form("cfgform"):
        a, b, c = st.columns(3)
        seed = a.number_input("Random seed", 0, 10**9, int(cfg.seed))
        duration = b.number_input("Simulation length (min)", 60, 2880, int(cfg.duration_min), step=60)
        rate = c.number_input("Base demand (arrivals/hour)", 0.0, 500.0, float(cfg.base_arrivals_per_hour), step=5.0)
        a, b, c = st.columns(3)
        peak = a.number_input("Peak factor (1 = flat)", 1.0, 10.0, float(cfg.peak_factor), step=0.1)
        var = b.slider("Demand variation", 0.0, 1.0, float(cfg.demand_variation))
        mdur = c.number_input("Mean parking duration (min)", 15.0, 600.0, float(cfg.mean_duration_min), step=15.0)
        a, b, c = st.columns(3)
        pat = a.number_input("Mean patience (min, 0 = leave at once)", 0.0, 120.0, float(cfg.patience_mean_min))
        ev = b.slider("EV share", 0.0, 0.5, float(cfg.ev_share))
        acc = c.slider("Accessible-permit share", 0.0, 0.3, float(cfg.accessible_share))
        st.markdown("**Car park capacity (spaces)**")
        cps = []
        for cp in cfg.car_parks:
            x = st.columns([2, 1, 1, 1])
            x[0].markdown(f"{cp.name}<br><span class='note'>gate {cp.gate_distance_m:.0f} m · walk {cp.walk_base_m:.0f} m</span>", unsafe_allow_html=True)
            s_ = x[1].number_input("Standard", 0, 1000, cp.standard, key=f"s_{cp.name}")
            e_ = x[2].number_input("EV", 0, 200, cp.ev, key=f"e_{cp.name}")
            a_ = x[3].number_input("Accessible", 0, 100, cp.accessible, key=f"a_{cp.name}")
            cps.append(dataclasses.replace(cp, standard=int(s_), ev=int(e_), accessible=int(a_)))
        if st.form_submit_button("Apply configuration", disabled=disabled):
            try:
                new = dataclasses.replace(cfg, seed=int(seed), duration_min=int(duration), base_arrivals_per_hour=rate,
                                          peak_factor=peak, demand_variation=var, mean_duration_min=mdur,
                                          patience_mean_min=pat, ev_share=ev, accessible_share=acc, car_parks=cps)
                ss.cfg = new.validate()
                ss.sim = None
                flash("ok", "Configuration applied (simulation reset).")
                st.rerun()
            except ConfigError as exc:
                st.error(str(exc))
    d1, d2 = st.columns(2)
    d1.download_button("⬇ Export active configuration (JSON)", json.dumps(ss.cfg.to_dict(), indent=2),
                       f"{ss.cfg.name}.json", "application/json", width="stretch")
    up = d2.file_uploader("Import configuration (JSON)", type="json", disabled=disabled)
    if up is not None:
        try:
            ss.cfg = config_from_dict(json.loads(up.getvalue()))
            ss.sim = None
            st.success(f"Imported '{ss.cfg.name}'.")
        except (ConfigError, json.JSONDecodeError) as exc:
            st.error(f"Could not import: {exc}")
    with st.expander("Active configuration"):
        st.json(ss.cfg.to_dict())


def space_grid(cp) -> str:
    cells = []
    for s in cp.spaces:
        cls = "free" if s.available else "occ"
        tip = f"{s.space_id} {s.space_type} {'free' if s.available else 'occupied by ' + str(s.occupant)}"
        cells.append(f"<div class='sp {cls}' title='{tip}'>{s.space_type[0].upper()}</div>")
    return "<div class='grid'>" + "".join(cells) + "</div>"


def page_inspector() -> None:
    sim = st.session_state.sim
    st.subheader("Agent and car-park inspection")
    if sim is None:
        st.info("Run or step a simulation first (Simulation page).")
        return
    for cp in sim.car_parks:
        st.markdown(f"**{cp.name}** — {cp.occupied}/{cp.capacity} occupied ({cp.occupancy_ratio:.0%}); free: "
                    f"standard {cp.free_count('standard')}, EV {cp.free_count('ev')}, accessible {cp.free_count('accessible')}")
        st.progress(cp.occupancy_ratio)
        st.markdown(space_grid(cp), unsafe_allow_html=True)
    st.caption("Legend: letter = space type (S standard, E EV bay, A accessible); filled dark = occupied, white = free. "
               "Hover a square for its identifier.")
    t1, t2, t3 = st.tabs(["Decision log", "Vehicles", "Messages"])
    with t1:
        d = pd.DataFrame(sim.decisions)
        if d.empty:
            st.info("No decisions logged yet.")
        else:
            f1, f2 = st.columns(2)
            outc = f1.multiselect("Outcome", ["allocated", "not_allocated"], ["allocated", "not_allocated"])
            vtypes = f2.multiselect("Vehicle type", ["standard", "ev", "accessible"], ["standard", "ev", "accessible"])
            d = d[d.outcome.isin(outc) & d.vehicle_type.isin(vtypes)]
            st.dataframe(d.tail(200).iloc[::-1][["time", "vehicle_id", "vehicle_type", "strategy", "attempt", "outcome",
                                               "space_id", "n_candidates", "offers_declined", "score", "reason"]],
                         width="stretch", hide_index=True)
            st.download_button("⬇ Download decision log (CSV)", pd.DataFrame(sim.decisions).to_csv(index=False), "decision_log.csv")
    with t2:
        v = sim.vehicle_table()
        st.dataframe(v.tail(300), width="stretch", hide_index=True) if not v.empty else st.info("No vehicles yet.")
    with t3:
        st.write(sim.bus.counts or "No messages yet.")
        st.caption("Centralised request → availability query/reply → offer → accept/decline messages. Not a decentralised protocol.")


def results_dirs() -> list[Path]:
    base = ROOT / "results"
    return sorted([p.parent for p in base.glob("**/runs.csv")]) if base.exists() else []


def page_analytics() -> None:
    st.subheader("Analytics")
    dirs = results_dirs()
    if not dirs:
        st.info("No saved experiment results found. Run `REPRODUCE_RESULTS.bat` or use the **Experiments** page.")
        return
    d = st.selectbox("Results folder", dirs, format_func=lambda p: str(p.relative_to(ROOT)))
    try:
        res = analytics.load_results(d)
    except analytics.ResultsError as exc:
        st.error(str(exc))
        return
    meta = res["meta"]
    st.caption(f"{meta.get('data_origin')} · mode **{meta.get('mode')}** · {meta.get('replications')} replications · "
               f"base seed {meta.get('base_seed')} · created {meta.get('created_utc')}")
    summ, comp = analytics.summarise(res["runs"]), analytics.compare_strategies(res["runs"])
    tab = st.tabs(["Charts", "Summary table", "Paired comparison", "Raw runs"])
    with tab[0]:
        name = st.selectbox("Chart", list(analytics.FIGURES), format_func=lambda s: s.replace("_", " ").capitalize())
        fig = analytics.FIGURES[name](res)
        st.pyplot(fig)
        analytics.plt.close(fig)
    with tab[1]:
        wide = summ.pivot_table(index=["scenario", "metric"], columns="strategy", values="mean")
        st.dataframe(summ, width="stretch", hide_index=True)
        st.download_button("⬇ Summary CSV", summ.to_csv(index=False), "summary.csv")
        del wide
    with tab[2]:
        st.caption("Coordinated − baseline, paired by seed. d_z = Cohen's d for paired samples. Holm correction across metrics within a scenario. "
                   "Empty cells = not computable (see note).")
        st.dataframe(comp, width="stretch", hide_index=True)
        st.download_button("⬇ Comparison CSV", comp.to_csv(index=False), "comparison.csv")
    with tab[3]:
        st.dataframe(res["runs"], width="stretch", hide_index=True)
        st.download_button("⬇ Per-run CSV", res["runs"].to_csv(index=False), "runs.csv")


def page_experiments() -> None:
    ss = st.session_state
    st.subheader("Experiment comparison")
    st.write("Runs **baseline** and **coordinated** on identical synthetic arrival streams (paired seeds) and reports "
             "uncertainty across replications.")
    if ss.playing:
        st.warning("A live simulation is playing. Pause it before starting an experiment (prevents conflicting jobs).")
        return
    pre = predefined_scenarios()
    names = st.multiselect("Scenarios", list(pre), ["moderate_demand", "high_demand"])
    reps = st.number_input("Replications per scenario", 2, 100, 5)
    seed = st.number_input("Base seed", 0, 10**6, 2026)
    if st.button("Run experiment", type="primary", disabled=not names):
        out = ROOT / "results" / "ui_runs" / datetime.now().strftime("run_%Y%m%d_%H%M%S")
        bar = st.progress(0.0, text="Starting…")
        try:
            run_experiment([pre[n] for n in names], int(reps), int(seed), out, mode="ui",
                           progress=lambda a, b, m: bar.progress(a / b, text=f"{m} ({a}/{b})"))
            analytics.analyse(out)
        except Exception as exc:  # shown to the user, not swallowed
            st.error(f"Experiment failed: {exc}")
            return
        bar.empty()
        ss.last_exp = str(out)
        st.success(f"Finished. Saved to {out.relative_to(ROOT)}")
    if ss.get("last_exp"):
        res = analytics.load_results(ss.last_exp)
        comp = analytics.compare_strategies(res["runs"], ["success_rate", "mean_wait_min", "mean_drive_m", "mean_walk_m", "co2e_proxy_kg"])
        st.dataframe(comp, width="stretch", hide_index=True)
        fig = analytics.fig_strategy_comparison(res)
        st.pyplot(fig)
        analytics.plt.close(fig)
        st.info("How to read: a negative mean difference means coordinated is lower. CI that spans 0 → no clear difference at this sample size. "
                "Simulation results depend on the modelling assumptions in Methodology.")
    st.caption("Experiments need results to persist: they are written to results/ui_runs/.")


def page_methodology() -> None:
    st.subheader("Methodology and documentation")
    st.markdown("""
**Agents.** Vehicle, Parking-space, Car-park and Management agents exchange explicit messages
(request → availability query/reply → offer → accept/decline). Coordination is centralised; there is no decentralised negotiation.

**Strategies.** *Baseline*: first eligible free space in fixed car-park order. *Coordinated*: lowest weighted cost of drive distance,
walk distance (×3 for accessible permit holders), car-park congestion, with credits for EV→EV bay and accessible→accessible bay.

**Time.** Simulated minutes advance event-to-event; wall-clock time is only used for decision compute time.

**Data.** All demand data are synthetic (non-homogeneous Poisson arrivals). No real car park, driver or sensor data is used.

**Sustainability proxy.** CO₂e proxy = in-park drive km × g/km + idle waiting minutes × g/min, with *illustrative* factors. It is not measured impact,
and walking distance is not counted. Higher utilisation alone is **not** evidence of environmental benefit.

**Limitations.** Single destination per car park, no cruising between car parks, deterministic driver walking limits, no pricing/reservations, synthetic parameters not calibrated to reality.
""")
    docs = sorted((ROOT / "docs").glob("*.md"))
    if docs:
        sel = st.selectbox("Project documentation", docs, format_func=lambda p: p.name)
        st.markdown(sel.read_text(encoding="utf-8"))


def main() -> None:
    init_state()
    with st.sidebar:
        st.markdown("### 🅿️ Parking MAS")
        page = st.radio("Navigate", PAGES, label_visibility="collapsed")
        st.caption("Muhammad Faryad · Keele University\nSupervisor: Dr Thomas Neligwa")
        st.caption("Synthetic data only.")
    hero()
    {"Overview": page_overview, "Simulation": page_simulation, "Scenarios": page_scenarios, "Inspector": page_inspector,
     "Analytics": page_analytics, "Experiments": page_experiments, "Methodology": page_methodology}[page]()


main()
