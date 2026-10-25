"""Budget for the fixed Medium w8a8/SAME-L runtime; no heavy imports.

Previous complete upload measured a 2,018.3 MiB process-tree peak on this PC.
Keep a 2.5 GiB inference budget, 1.25 GiB Windows reserve and 0.5 GiB margin.
The model worker remains globally serialized and enforces the reserve live.
"""
START_AVAILABLE_GIB = 4.25
RUNTIME_RESERVE_GIB = 1.25


def memory_budget(available_bytes):
    return {'available_gib': round(available_bytes / 1024**3, 3),
        'start_required_gib': START_AVAILABLE_GIB,
        'model_budget_gib': 2.5, 'runtime_reserve_gib': RUNTIME_RESERVE_GIB,
        'extra_margin_gib': 0.5,
        'can_start': available_bytes >= START_AVAILABLE_GIB * 1024**3}
