import pytest
from helpers import tiny_cfg

from parking_mas.model import AllocationError, CarParkAgent, ManagementAgent, ParkingSpaceAgent, UnknownVehicleError, VehicleAgent
from parking_mas.strategies import make_strategy


def mk_manager(strategy="baseline", cfg=None):
    cfg = cfg or tiny_cfg()
    cps = [CarParkAgent(c, i) for i, c in enumerate(cfg.car_parks)]
    return ManagementAgent(cps, make_strategy(strategy, cfg)), cps, cfg


def veh(i, vt="standard", walk=5000.0):
    return VehicleAgent(f"V{i}", vt, 0, 60, 0, walk)


def test_space_state_transitions():
    s = ParkingSpaceAgent("S1", "A", "standard", 0, 100, 100)
    assert s.available
    s.occupy("V1", 0)
    assert not s.available
    with pytest.raises(AllocationError):
        s.occupy("V2", 1)  # double occupation
    with pytest.raises(AllocationError):
        s.release("V2", 2)  # wrong vehicle
    s.release("V1", 3)
    with pytest.raises(AllocationError):
        s.release("V1", 4)  # already free
    assert [h[1] for h in s.history] == ["occupy", "release"]


def test_car_park_layout_and_capacity():
    m, cps, _ = mk_manager()
    a = cps[0]
    assert a.capacity == 4 and [s.space_type for s in a.spaces] == ["accessible", "standard", "standard", "ev"]
    assert m.capacity == 6
    assert a.spaces[0].drive_m == 100 and a.spaces[1].walk_m == 300 + 1 * 4.0


def test_eligibility_rules():
    m, cps, _ = mk_manager()
    a = cps[0]
    std_types = {c.space.space_type for c in a.query("standard")}
    ev_types = {c.space.space_type for c in a.query("ev")}
    acc_types = {c.space.space_type for c in a.query("accessible")}
    assert std_types == {"standard"} and ev_types == {"ev", "standard"} and acc_types == {"accessible", "standard"}


def test_allocation_release_and_unknown_departure():
    m, cps, _ = mk_manager()
    v = veh(1)
    d = m.request_parking(v, 0)
    assert d.success and m.occupied == 1
    m.check_invariants()
    sp = m.release("V1", 10)
    assert sp is d.chosen and m.occupied == 0
    with pytest.raises(UnknownVehicleError):
        m.release("V1", 11)  # already departed
    with pytest.raises(UnknownVehicleError):
        m.release("nobody", 11)


def test_duplicate_allocation_rejected_state_unchanged():
    m, _, _ = mk_manager()
    v = veh(1)
    m.request_parking(v, 0)
    with pytest.raises(AllocationError):
        m.request_parking(v, 1)
    assert m.occupied == 1
    m.check_invariants()


def test_full_capacity_failure_does_not_corrupt_state():
    m, _, _ = mk_manager()
    ok = [m.request_parking(veh(i), 0).success for i in range(4)]  # 4 standard spaces
    assert all(ok)
    d = m.request_parking(veh(99), 1)
    assert not d.success and d.reason == "no eligible space free" and m.occupied == 4
    m.check_invariants()


def test_reserved_spaces_not_given_to_standard_vehicles():
    m, cps, _ = mk_manager()
    for i in range(4):
        m.request_parking(veh(i), 0)
    assert cps[0].free_count("ev") == 1 and cps[0].free_count("accessible") == 1


def test_direct_allocate_of_occupied_or_ineligible_space_fails():
    m, cps, _ = mk_manager()
    a = cps[0]
    sp = a.spaces[1]
    a.allocate(sp, "V1", "standard", 0)
    with pytest.raises(AllocationError):
        a.allocate(sp, "V2", "standard", 0)
    with pytest.raises(AllocationError):
        a.allocate(a.spaces[3], "V3", "standard", 0)  # EV bay
    assert a.occupied == 1


def test_baseline_is_first_available_in_fixed_order():
    m, cps, _ = mk_manager("baseline")
    d = m.request_parking(veh(1), 0)
    assert d.chosen.car_park == "A" and d.chosen.index == 1  # first standard in car park A
    assert "first eligible" in d.reason


def test_coordinated_prefers_ev_bay_and_lower_cost():
    m, cps, _ = mk_manager("coordinated")
    d = m.request_parking(veh(1, "ev"), 0)
    assert d.chosen.space_type == "ev"
    mb, _, _ = mk_manager("baseline")
    assert mb.request_parking(veh(1, "ev"), 0).chosen.space_type == "standard"  # baseline ignores EV bays


def test_coordinated_matches_brute_force_minimum():
    cfg = tiny_cfg()
    m, cps, _ = mk_manager("coordinated", cfg)
    strat = m.strategy
    for i in range(3):
        m.request_parking(veh(i), 0)
    v = veh(50, "ev")
    from parking_mas.model import Candidate
    brute = min((strat.cost(v, Candidate(s, cp.occupancy_ratio)), cp.order, s.index, s)
                for cp in cps for s in cp.all_free_spaces("ev"))
    assert m.request_parking(v, 1).chosen is brute[3]


def test_vehicle_declines_offer_beyond_walk_limit_and_gets_next():
    m, cps, _ = mk_manager("baseline")
    v = veh(1, walk=250.0)  # A walks 300+, B walks 100+
    d = m.request_parking(v, 0)
    assert d.success and d.chosen.car_park == "B" and d.declined == 1


def test_all_offers_declined_reports_reason():
    m, _, _ = mk_manager()
    d = m.request_parking(veh(1, walk=10.0), 0)
    assert not d.success and "declined" in d.reason and m.occupied == 0


def test_unknown_strategy():
    from parking_mas.config import ConfigError
    with pytest.raises(ConfigError):
        make_strategy("magic", tiny_cfg())


def test_messages_recorded():
    m, _, _ = mk_manager()
    m.request_parking(veh(1), 0)
    assert m.bus.counts["request"] == 1 and m.bus.counts["accept"] == 1 and m.bus.counts["availability_query"] == 2
