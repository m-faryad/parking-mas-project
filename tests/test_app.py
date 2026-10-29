from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


def _at():
    return AppTest.from_file(APP, default_timeout=90).run()


def test_app_starts_and_all_pages_render():
    at = _at()
    assert not at.exception
    for page in ["Simulation", "Scenarios", "Inspector", "Analytics", "Experiments", "Methodology", "Overview"]:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page


def test_run_to_end_then_inspect():
    at = _at()
    at.sidebar.radio[0].set_value("Simulation").run()
    [b for b in at.button if "Run to end" in b.label][0].click().run()
    assert not at.exception and len(at.metric) >= 10
    assert at.session_state["sim"].finished
    at.sidebar.radio[0].set_value("Inspector").run()
    assert not at.exception


def test_step_and_reset_buttons():
    at = _at()
    at.sidebar.radio[0].set_value("Simulation").run()
    [b for b in at.button if "Step" in b.label][0].click().run()
    assert at.session_state["sim"].now == 30
    [b for b in at.button if "Reset" in b.label][0].click().run()
    assert at.session_state["sim"] is None


def test_invalid_scenario_input_shows_error_not_crash():
    at = _at()
    at.sidebar.radio[0].set_value("Scenarios").run()
    # EV + accessible shares cannot exceed 1 only via config; here make capacity of every car park zero
    for ni in at.number_input:
        if ni.key and ni.key.startswith(("s_", "e_", "a_")):
            ni.set_value(0)
    [b for b in at.button if "Apply" in b.label][0].click().run()
    assert at.error and "capacity" in at.error[0].value
