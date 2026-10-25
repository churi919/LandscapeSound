"""Resource budget boundaries; no model execution or external requests."""
from audio_model.memory_budget import memory_budget


def test_medium_budget_preserves_os_reserve_and_extra_margin():
    budget = memory_budget(4.25 * 1024**3)
    assert budget['can_start']
    assert budget['start_required_gib'] == (budget['model_budget_gib']
        + budget['runtime_reserve_gib'] + budget['extra_margin_gib'])
    assert budget['runtime_reserve_gib'] == 1.25


def test_medium_budget_rejects_insufficient_room_before_model_start():
    assert not memory_budget(4.25 * 1024**3 - 1)['can_start']
    assert not memory_budget(3 * 1024**3)['can_start']
