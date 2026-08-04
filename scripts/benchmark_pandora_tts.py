from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_TEXTS = {
    "short": "Merhaba, ben Pandora. Bugün senin için ne yapabilirim?",
    "medium": (
        "Prometheus Core üzerindeki görev tamamlandı. Dört dosya değiştirildi ve "
        "tüm doğrulama testleri başarıyla geçti. Değişikliklerin ayrıntıları ekranda hazır."
    ),
    "long": (
        "Prometheus Core, yazılım geliştirme görevlerini güvenli ve izlenebilir biçimde "
        "yönetmek için tasarlanmıştır. Pandora bu çekirdeğin mobil ve sesli arayüzüdür. "
        "Günlük sorulara doğal biçimde yanıt verir, güncel bilgileri kaynaklarıyla özetler "
        "ve teknik görevlerde yapılacak değişiklikleri önce açıkça anlatır. Dosya değiştiren "
        "veya komut çalıştıran işlemler yalnızca ekrandaki güvenli onaydan sonra ilerler. "
        "Böylece konuşmanın rahatlığı korunurken kritik eylemlerde denetim kullanıcıda kalır."
    ),
}


def _local_app_data() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    return Path(raw) if raw else Path.home() / ".local" / "share"


def _request(url: str, token: str, *, payload: dict | None = None) -> tuple[bytes, dict[str, str]]:
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read(), {key.lower(): value for key, value in response.headers.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-file",
        default=str(_local_app_data() / "Prometheus" / "runtime" / "pandora_tts_worker.json"),
    )
    parser.add_argument(
        "--output",
        default=str(_local_app_data() / "Prometheus" / "pandora_voice" / "runtime_benchmark.json"),
    )
    args = parser.parse_args()

    state_path = Path(args.state_file)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    host = str(state["host"])
    port = int(state["port"])
    token = str(state["token"])
    if host not in {"127.0.0.1", "::1"}:
        raise SystemExit("Worker state is not loopback-only")
    base = f"http://{host}:{port}"

    _request(base + "/load", token, payload={})
    results = {}
    for name, text in DEFAULT_TEXTS.items():
        started = time.perf_counter()
        audio, headers = _request(
            base + "/synthesize",
            token,
            payload={"text": text, "mode": "normal", "allow_cache": False},
        )
        elapsed = time.perf_counter() - started
        duration = float(headers["x-pandora-duration-seconds"])
        generation = float(headers["x-pandora-generation-seconds"])
        results[name] = {
            "response_seconds": round(elapsed, 3),
            "generation_seconds": round(generation, 3),
            "audio_seconds": round(duration, 3),
            "rtf": round(generation / duration, 3) if duration else None,
            "bytes": len(audio),
        }

    _, metric_headers = _request(base + "/metrics", token)
    metrics_body, _ = _request(base + "/metrics", token)
    metrics = json.loads(metrics_body)

    gates = {
        "short_response_seconds_lte_4": results["short"]["response_seconds"] <= 4.0,
        "medium_rtf_lte_1_25": results["medium"]["rtf"] is not None and results["medium"]["rtf"] <= 1.25,
        "long_rtf_lte_1_25": results["long"]["rtf"] is not None and results["long"]["rtf"] <= 1.25,
        "peak_reserved_vram_lte_3800": int(metrics.get("process_peak_reserved_mib", 99999)) <= 3800,
    }
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "worker": {"host": host, "port": port},
        "results": results,
        "metrics": metrics,
        "gates": gates,
        "all_gates_passed": all(gates.values()),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_gates_passed"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        raise SystemExit(f"Pandora benchmark failed: {exc}") from exc
