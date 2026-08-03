from __future__ import annotations

import json

from app.improvement.benchmark import ImprovementBenchmark


if __name__ == "__main__":
    print(
        json.dumps(
            ImprovementBenchmark().run(),
            ensure_ascii=False,
            indent=2,
        )
    )
