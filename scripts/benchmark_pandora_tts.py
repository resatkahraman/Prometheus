from __future__ import annotations

import argparse
import json
import os
import sys
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
    parser = argparse.ArgumentParser(description="Run Pandora Local Voice RTX 3050 Ti runtime benchmark.")
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
    if not state_path.is_file():
        report = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "terminal_status": "ENVIRONMENT_INVALID",
            "error": f"Worker state file missing: {state_path}",
            "all_gates_passed": False,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        report = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "terminal_status": "ENVIRONMENT_INVALID",
            "error": f"Worker state file unreadable: {exc}",
            "all_gates_passed": False,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    host = str(state.get("host", "127.0.0.1"))
    port = int(state.get("port", 9723))
    token = str(state.get("token", ""))
    if host not in {"127.0.0.1", "::1"}:
        report = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "terminal_status": "ENVIRONMENT_INVALID",
            "error": "Worker state is not loopback-only",
            "all_gates_passed": False,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    base = f"http://{host}:{port}"

    try:
        cold_start_begin = time.perf_counter()
        _request(base + "/load", token, payload={})
        cold_load_seconds = round(time.perf_counter() - cold_start_begin, 3)
    except Exception as exc:
        report = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "terminal_status": "ENVIRONMENT_INVALID",
            "error": f"Worker load failed: {exc}",
            "all_gates_passed": False,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    results = {}
    wav_output_dir = Path(args.output).parent / "benchmark_audio"
    wav_output_dir.mkdir(parents=True, exist_ok=True)

    for name, text in DEFAULT_TEXTS.items():
        started = time.perf_counter()
        try:
            audio, headers = _request(
                base + "/synthesize",
                token,
                payload={"text": text, "mode": "normal", "allow_cache": False},
            )
        except Exception as exc:
            report = {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "terminal_status": "QUALITY_REJECTED",
                "error": f"Synthesis failed for '{name}': {exc}",
                "all_gates_passed": False,
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2

        elapsed = time.perf_counter() - started
        duration = float(headers.get("x-pandora-duration-seconds", 0.0))
        generation = float(headers.get("x-pandora-generation-seconds", 0.0))
        wav_file = wav_output_dir / f"benchmark_{name}.wav"
        wav_file.write_bytes(audio)

        results[name] = {
            "response_seconds": round(elapsed, 3),
            "generation_seconds": round(generation, 3),
            "audio_seconds": round(duration, 3),
            "rtf": round(generation / duration, 3) if duration > 0 else None,
            "bytes": len(audio),
            "wav_path": str(wav_file),
        }

    try:
        metrics_body, _ = _request(base + "/metrics", token)
        metrics = json.loads(metrics_body)
    except Exception:
        metrics = {}

    short_ok = results["short"]["response_seconds"] <= 4.0
    medium_ok = results["medium"]["rtf"] is not None and results["medium"]["rtf"] <= 1.25
    long_ok = results["long"]["rtf"] is not None and results["long"]["rtf"] <= 1.25
    peak_vram = int(metrics.get("process_peak_reserved_mib", 0))
    vram_ok = peak_vram <= 3800

    gates = {
        "short_response_seconds_lte_4": short_ok,
        "medium_rtf_lte_1_25": medium_ok,
        "long_rtf_lte_1_25": long_ok,
        "peak_reserved_vram_lte_3800": vram_ok,
    }

    all_passed = all(gates.values())
    if not vram_ok:
        terminal_status = "RUNTIME_MEMORY_BLOCKED"
    elif not (short_ok and medium_ok and long_ok):
        terminal_status = "QUALITY_REJECTED"
    else:
        terminal_status = "SUCCESS"

    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "terminal_status": terminal_status,
        "cold_load_seconds": cold_load_seconds,
        "worker": {"host": host, "port": port},
        "results": results,
        "metrics": metrics,
        "gates": gates,
        "all_gates_passed": all_passed,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0 if all_passed else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        err_report = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "terminal_status": "ENVIRONMENT_INVALID",
            "error": str(exc),
            "all_gates_passed": False,
        }
        print(json.dumps(err_report, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
