"""Settings for the grounding test: endpoint, models, prices and decision thresholds.

Sources: dev.meta.ai docs (models, pricing, computer use, image understanding),
read 27-28/10/2026. Thresholds come from GROUNDING_TEST_PLAN.md section 8,
accepted by the founder on 28/10/2026 (latency limit 5 s).
"""

BASE_URL = "https://api.meta.ai/v1"
REQUEST_TIMEOUT_S = 120

# Short name -> model id. Contributor variants are deliberately absent:
# Meta may train on content sent to them.
MODELS = {
    "spark": "muse-spark-1.3",
    "wonder": "muse-wonder-1.0",
}

# (model short name, method). M1 = computer use, M2 = image understanding + JSON.
# Wonder only runs M1, as in the plan.
DEFAULT_COMBOS = [("spark", "m1"), ("spark", "m2"), ("wonder", "m1")]

# USD per 1M tokens, Standard tier.
PRICES = {
    "muse-spark-1.3": {"input": 1.25, "cached": 0.15, "output": 4.25},
    "muse-wonder-1.0": {"input": 4.00, "cached": 0.20, "output": 20.00},
}

# Scoring.
NEAR_PX = 12  # "near" = outside the box but within this many px of its edge, on the original image

# Decision thresholds for the 12 real cases.
CASES_TOTAL = 12
ADOPT_MIN_HITS = 10
REJECT_MAX_HITS = 7
LATENCY_LIMIT_S = 5.0

# Rough token guess per call, only for the pre-run estimate.
EST_INPUT_TOKENS = 2500
EST_OUTPUT_TOKENS = 300
