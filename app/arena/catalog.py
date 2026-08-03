from __future__ import annotations

from pathlib import PurePosixPath

from app.arena.models import ArenaScenario, ArenaVerification


_SCENARIOS = (
    ArenaScenario(
        id="calculator_from_scratch",
        title="Kısa istekten sıfırdan hesap makinesi",
        goal=(
            "Bana profesyonel, responsive ve klavyeyle kullanılabilen bir hesap "
            "makinesi yap. Uygulama vanilla HTML, CSS ve JavaScript kullansın. "
            "Dört temel işlem, ondalık sayılar, işaret değiştirme, yüzde, temizleme "
            "ve sıfıra bölme hata durumunu desteklesin. Hesaplama mantığını DOM'dan "
            "ayır; saf motor calculate(a, operator, b), percent(value) ve "
            "toggleSign(value) fonksiyonlarını dışa aktarsın. calculate; sıfıra "
            "bölme, geçersiz operatör ve sonlu olmayan girdilerde exception "
            "fırlatsın. Birim testleri yaz "
            "ve üretim derlemesini doğrula. "
            "Yeni framework, bağımlılık veya Git kullanma."
        ),
        seed_files={
            "test/real-world.contract.test.js": """import test from "node:test";
import assert from "node:assert/strict";
import {
  calculate,
  percent,
  toggleSign,
} from "../src/calculator.js";

test("supports the four arithmetic operations", () => {
  assert.equal(calculate(7, "+", 5), 12);
  assert.equal(calculate(7, "-", 5), 2);
  assert.equal(calculate(7, "*", 5), 35);
  assert.equal(calculate(10, "/", 4), 2.5);
});

test("supports percentage and sign changes", () => {
  assert.equal(percent(250), 2.5);
  assert.equal(toggleSign(12.5), -12.5);
  assert.equal(toggleSign(-3), 3);
});

test("rejects division by zero, invalid operators and non-finite values", () => {
  assert.throws(() => calculate(1, "/", 0));
  assert.throws(() => calculate(1, "^", 2));
  assert.throws(() => calculate(Number.NaN, "+", 2));
});
""",
        },
        required_paths=(
            "package.json",
            "index.html",
            "styles.css",
            "src/app.js",
            "src/calculator.js",
            "tests/calculator.test.js",
        ),
        protected_paths=("test/real-world.contract.test.js",),
        verifications=(
            ArenaVerification(
                name="Gizli davranış sözleşmesi",
                preset="node_test",
                extra_args=("test/real-world.contract.test.js",),
            ),
            ArenaVerification(
                name="DOM uygulaması sözdizimi",
                preset="node_check",
                extra_args=("src/app.js",),
            ),
            ArenaVerification(
                name="Hesaplama motoru sözdizimi",
                preset="node_check",
                extra_args=("src/calculator.js",),
            ),
        ),
        max_model_calls=24,
        max_estimated_input_tokens=60_000,
        target_model_calls=12,
        target_total_tokens=32_000,
        minimum_calls_to_start=1,
        timeout_seconds=900,
        initial_verification_should_fail=True,
        required_agents=("frontend", "integration"),
        minimum_handoffs=4,
    ),
    ArenaScenario(
        id="existing_vanilla_repair",
        title="Mevcut vanilla uygulamada hedefli onarım",
        goal=(
            "Mevcut vanilla hesap makinesindeki yüzde hesaplama hatasını düzelt. "
            "Yalnızca src/calculator.js dosyasını değiştir; proje yapısını, testleri "
            "ve eski src/components/LegacyCalculator.tsx dosyasını değiştirme. "
            "Yeni framework veya bağımlılık ekleme. `npm test` ve `npm run build` "
            "tamamen geçsin. Git kullanma."
        ),
        seed_files={
            "package.json": """{
  "name": "prometheus-real-world-vanilla-repair",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test",
    "build": "node --check src/app.js"
  }
}
""",
            "index.html": """<!doctype html>
<html lang="tr">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hesap Makinesi</title>
    <link rel="stylesheet" href="./styles.css">
  </head>
  <body>
    <main><output id="result">0</output></main>
    <script type="module" src="./src/app.js"></script>
  </body>
</html>
""",
            "styles.css": """body {
  display: grid;
  min-height: 100vh;
  margin: 0;
  place-items: center;
  font-family: system-ui, sans-serif;
}
""",
            "src/app.js": """import { percentageOf } from "./calculator.js";

const output = document.querySelector("#result");
if (output) {
  output.value = String(percentageOf(200, 15));
}
""",
            "src/calculator.js": """export function percentageOf(value, percent) {
  if (!Number.isFinite(value) || !Number.isFinite(percent)) {
    throw new TypeError("value and percent must be finite numbers");
  }
  return value - percent;
}
""",
            "src/components/LegacyCalculator.tsx": """// Kept only as migration history.
export function LegacyCalculator() {
  return null;
}
""",
            "test/calculator.contract.test.js": """import test from "node:test";
import assert from "node:assert/strict";
import { percentageOf } from "../src/calculator.js";

test("calculates a percentage of a value", () => {
  assert.equal(percentageOf(200, 15), 30);
  assert.equal(percentageOf(50, 10), 5);
});

test("supports zero, negative values and decimal percentages", () => {
  assert.equal(percentageOf(500, 0), 0);
  assert.equal(percentageOf(-80, 25), -20);
  assert.equal(percentageOf(40, 12.5), 5);
});

test("rejects non-finite inputs", () => {
  assert.throws(() => percentageOf(Number.NaN, 10), TypeError);
  assert.throws(() => percentageOf(10, Number.POSITIVE_INFINITY), TypeError);
});
""",
        },
        required_paths=("src/calculator.js",),
        protected_paths=(
            "package.json",
            "index.html",
            "styles.css",
            "src/app.js",
            "src/components/LegacyCalculator.tsx",
            "test/calculator.contract.test.js",
        ),
        verifications=(
            ArenaVerification(name="Node testleri", preset="npm_test"),
            ArenaVerification(name="Üretim kontrolü", preset="npm_build"),
        ),
        max_model_calls=10,
        max_estimated_input_tokens=24_000,
        target_model_calls=5,
        target_total_tokens=12_000,
        minimum_calls_to_start=1,
        timeout_seconds=480,
    ),
    ArenaScenario(
        id="js_bugfix",
        title="JavaScript hata düzeltme",
        goal=(
            "Bu küçük JavaScript projesindeki indirim hesaplama hatasını düzelt. "
            "Yalnızca src/discount.js dosyasını değiştir; package.json ve test "
            "dosyalarını değiştirme. Mevcut davranış sözleşmesini koru ve "
            "`npm test` komutunun tamamen geçmesini sağla. Git kullanma."
        ),
        seed_files={
            "package.json": """{
  "name": "prometheus-arena-js-bugfix",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test"
  }
}
""",
            "src/discount.js": """export function discountedPrice(price, percent) {
  if (!Number.isFinite(price) || price < 0) {
    throw new TypeError("price must be a non-negative number");
  }
  if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
    throw new RangeError("percent must be between 0 and 100");
  }
  return price - percent;
}
""",
            "test/discount.test.js": """import test from "node:test";
import assert from "node:assert/strict";
import { discountedPrice } from "../src/discount.js";

test("applies a percentage discount", () => {
  assert.equal(discountedPrice(100, 20), 80);
  assert.equal(discountedPrice(50, 10), 45);
});

test("handles boundary discounts", () => {
  assert.equal(discountedPrice(50, 0), 50);
  assert.equal(discountedPrice(50, 100), 0);
});

test("rejects invalid inputs", () => {
  assert.throws(() => discountedPrice(-1, 10), TypeError);
  assert.throws(() => discountedPrice(10, 101), RangeError);
});
""",
        },
        required_paths=("src/discount.js",),
        protected_paths=("package.json", "test/discount.test.js"),
        verifications=(
            ArenaVerification(name="Node testleri", preset="npm_test"),
        ),
        max_model_calls=10,
        max_estimated_input_tokens=24_000,
        target_model_calls=5,
        target_total_tokens=12_000,
        minimum_calls_to_start=3,
        timeout_seconds=480,
    ),
    ArenaScenario(
        id="python_feature",
        title="Python özellik geliştirme",
        goal=(
            "text_stats.py dosyasına top_words(text, limit=3) fonksiyonunu ekle. "
            "Fonksiyon büyük/küçük harfi yok saymalı, yalnızca harf ve sayılardan "
            "oluşan sözcükleri saymalı, sonucu önce sıklığa sonra alfabetik sıraya "
            "göre (sözcük, adet) çiftleri olarak döndürmeli ve limit hatalarını "
            "doğrulamalı. Yalnızca text_stats.py dosyasını değiştir; testleri "
            "değiştirme. `pytest -q` tamamen geçsin. Git kullanma."
        ),
        seed_files={
            "text_stats.py": '''"""Small deterministic text helpers."""


def word_count(text: str) -> int:
    return len(text.split())
''',
            "tests/test_text_stats.py": """import pytest

from text_stats import top_words, word_count


def test_existing_word_count():
    assert word_count("one two three") == 3


def test_top_words_is_deterministic():
    assert top_words("Blue red blue GREEN green red blue", 2) == [
        ("blue", 3),
        ("green", 2),
    ]


def test_top_words_ignores_punctuation():
    assert top_words("Prometheus, prometheus! arena-2 arena2", 3) == [
        ("prometheus", 2),
        ("arena", 1),
        ("arena2", 1),
    ]


def test_top_words_validates_limit():
    with pytest.raises(ValueError):
        top_words("hello", 0)
""",
        },
        required_paths=("text_stats.py",),
        protected_paths=("tests/test_text_stats.py",),
        verifications=(
            ArenaVerification(
                name="Pytest",
                preset="pytest",
                extra_args=("-q",),
            ),
        ),
        max_model_calls=12,
        max_estimated_input_tokens=30_000,
        target_model_calls=6,
        target_total_tokens=16_000,
        minimum_calls_to_start=4,
        timeout_seconds=600,
    ),
    ArenaScenario(
        id="fastapi_status_contract_repair",
        title="FastAPI status sözleşmesini deterministik onar",
        goal=(
            "Mevcut FastAPI uygulamasındaki HTTP status sözleşmesi hatasını "
            "kanıta dayalı ve en düşük maliyetli yolla düzelt. Önce mevcut "
            "odaklı pytest sözleşmesini çalıştır; test başarılıysa hiçbir "
            "dosyayı değiştirme ve model çağrısı yapma. Test başarısızsa "
            "yalnızca src/status_api.py dosyasını değiştir. POST /items "
            "başarılı durumda HTTP 201, GET /items ise HTTP 200 döndürmeli. "
            "Mevcut testleri değiştirme. tests/test_status_api_contract.py "
            "dosyasını değiştirme. src/__init__.py dosyasını değiştirme. "
            "pyproject.toml dosyasını "
            "değiştirme. Yeni bağımlılık ekleme, Git "
            "kullanma ve son durumda odaklı pytest sözleşmesini tamamen geçir."
        ),
        seed_files={
            "src/__init__.py": "",
            "src/status_api.py": '''from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    application = FastAPI()
    items: list[dict[str, int | str]] = []

    @application.get("/items")
    def list_items() -> list[dict[str, int | str]]:
        return items

    @application.post("/items")
    def create_item() -> dict[str, int | str]:
        item = {"id": len(items) + 1, "name": "created"}
        items.append(item)
        return item

    return application


app = create_app()
''',
            "pyproject.toml": '''[tool.pytest.ini_options]
testpaths = ["tests"]
''',
            "tests/test_status_api_contract.py": '''from fastapi.testclient import TestClient

from src.status_api import create_app


def test_post_items_uses_created_status_and_get_remains_ok():
    client = TestClient(create_app())

    created = client.post("/items")
    assert created.status_code == 201
    assert created.json() == {"id": 1, "name": "created"}

    listed = client.get("/items")
    assert listed.status_code == 200
    assert listed.json() == [created.json()]
''',
        },
        required_paths=("src/status_api.py",),
        protected_paths=(
            "src/__init__.py",
            "pyproject.toml",
            "tests/test_status_api_contract.py",
        ),
        verifications=(
            ArenaVerification(
                name="FastAPI status sözleşmesi",
                preset="pytest",
                extra_args=("tests/test_status_api_contract.py",),
            ),
        ),
        max_model_calls=4,
        max_estimated_input_tokens=12_000,
        target_model_calls=1,
        target_total_tokens=4_000,
        minimum_calls_to_start=1,
        timeout_seconds=360,
        initial_verification_should_fail=True,
        required_agents=("backend",),
        minimum_handoffs=3,
    ),
    ArenaScenario(
        id="fastapi_task_api",
        title="FastAPI görev API teslimatı",
        goal=(
            "Bu küçük Python projesine gerçek bir FastAPI görev API'si ekle. "
            "Backend uzmanı yalnızca src/task_api.py dosyasını oluştursun. "
            "Modül create_app() fonksiyonunu ve uvicorn uyumlu module-level app "
            "nesnesini dışa aktarsın. Her create_app() çağrısı boş ve birbirinden "
            "bağımsız bir in-memory görev deposu üretmeli. GET /health tam olarak "
            "{\"status\":\"ok\"} döndürsün. GET /tasks görevleri oluşturulma "
            "sırasıyla liste halinde döndürsün. POST /tasks; title alanını baştaki "
            "ve sondaki boşluklardan arındırsın, boş veya 120 karakterden uzun "
            "başlığı HTTP 422 ile reddetsin ve başarılı durumda HTTP 201 ile "
            "id, title, completed=false alanlarını döndürsün. Kimlikler 1'den "
            "başlayan artan tam sayılar olsun. PATCH /tasks/{task_id}/complete "
            "görevi tamamlanmış olarak döndürsün; bulunmayan görev için HTTP 404 "
            "ve tam olarak 'Task not found' detail değeri versin. Backend işi "
            "tamamlandıktan sonra QA uzmanı yalnızca tests/test_task_api.py "
            "dosyasına en az dört anlamlı TestClient testi yazsın; sağlık ve boş "
            "listeyi, oluşturma/listeleme sırasını, tamamlama ile 404 durumunu ve "
            "422 doğrulamasını ayrı testlerde kapsasın. src/__init__.py "
            "dosyasını değiştirme. tests/test_task_api_backend_contract.py "
            "dosyasını değiştirme. tests/test_task_api_delivery_contract.py "
            "dosyasını değiştirme. pyproject.toml dosyasını değiştirme. "
            "Yeni bağımlılık "
            "ekleme, Git kullanma ve son durumda "
            "pytest -q komutunun tamamını geçir. Görevleri backend ve QA rollerine "
            "ayrı ayrı devret."
        ),
        seed_files={
            "src/__init__.py": "",
            "pyproject.toml": """[tool.pytest.ini_options]
testpaths = [\"tests\"]
""",
            "tests/test_task_api_backend_contract.py": '''from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.task_api import app, create_app


def test_module_exports_fastapi_app_and_fresh_factories():
    assert isinstance(app, FastAPI)

    first = TestClient(create_app())
    second = TestClient(create_app())

    assert first.get("/tasks").status_code == 200
    assert first.get("/tasks").json() == []
    assert second.get("/tasks").json() == []

    created = first.post("/tasks", json={"title": "First"})
    assert created.status_code == 201
    assert second.get("/tasks").json() == []


def test_health_create_list_complete_and_not_found_contract():
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    first = client.post("/tasks", json={"title": "  İlk görev  "})
    second = client.post("/tasks", json={"title": "İkinci görev"})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == {
        "id": 1,
        "title": "İlk görev",
        "completed": False,
    }
    assert second.json() == {
        "id": 2,
        "title": "İkinci görev",
        "completed": False,
    }

    listed = client.get("/tasks")
    assert listed.status_code == 200
    assert listed.json() == [first.json(), second.json()]

    completed = client.patch("/tasks/1/complete")
    assert completed.status_code == 200
    assert completed.json() == {
        "id": 1,
        "title": "İlk görev",
        "completed": True,
    }
    assert client.get("/tasks").json()[0]["completed"] is True

    missing = client.patch("/tasks/999/complete")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Task not found"}


def test_title_validation_contract():
    client = TestClient(create_app())

    for payload in ({}, {"title": ""}, {"title": "   "}):
        response = client.post("/tasks", json=payload)
        assert response.status_code == 422

    too_long = client.post("/tasks", json={"title": "x" * 121})
    assert too_long.status_code == 422
''',
            "tests/test_task_api_delivery_contract.py": '''from __future__ import annotations

import ast
from pathlib import Path


def test_qa_suite_is_material_and_covers_the_required_edges():
    path = Path("tests/test_task_api.py")
    assert path.is_file()

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    test_functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]

    assert len(test_functions) >= 4
    assert "TestClient" in source
    assert ".post(" in source
    assert ".get(" in source
    assert ".patch(" in source
    assert "404" in source
    assert "422" in source
''',
        },
        required_paths=(
            "src/task_api.py",
            "tests/test_task_api.py",
        ),
        protected_paths=(
            "src/__init__.py",
            "pyproject.toml",
            "tests/test_task_api_backend_contract.py",
            "tests/test_task_api_delivery_contract.py",
        ),
        verifications=(
            ArenaVerification(
                name="FastAPI sözleşme ve QA testleri",
                preset="pytest",
                extra_args=("-q",),
            ),
        ),
        max_model_calls=18,
        max_estimated_input_tokens=45_000,
        target_model_calls=9,
        target_total_tokens=24_000,
        minimum_calls_to_start=5,
        timeout_seconds=720,
        required_agents=("backend", "qa"),
        minimum_handoffs=4,
    ),
    ArenaScenario(
        id="test_authoring",
        title="Bağımsız test yazımı",
        goal=(
            "slugify.py için kapsamlı ve anlamlı pytest testleri oluştur. Üretim "
            "dosyasını değiştirme. Normal metin, Türkçe karakterler, tekrarlanan "
            "ayraçlar, baştaki/sondaki boşluklar ve boş sonuç durumunu kapsa. "
            "Testleri tests/test_slugify.py dosyasına yaz ve `pytest -q` komutunun "
            "geçmesini sağla. Git kullanma."
        ),
        seed_files={
            "slugify.py": """import re
import unicodedata


_TURKISH = str.maketrans({
    "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ş": "s", "Ş": "s",
    "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


def slugify(value: str) -> str:
    value = value.translate(_TURKISH).lower().strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")
""",
        },
        required_paths=("tests/test_slugify.py",),
        protected_paths=("slugify.py",),
        verifications=(
            ArenaVerification(
                name="Pytest",
                preset="pytest",
                extra_args=("-q",),
            ),
        ),
        max_model_calls=12,
        max_estimated_input_tokens=30_000,
        target_model_calls=6,
        target_total_tokens=16_000,
        minimum_calls_to_start=4,
        timeout_seconds=600,
    ),
    ArenaScenario(
        id="multi_agent_delivery",
        title="Çok uzmanlı teslimat",
        goal=(
            "Bu bağımlılıksız Node projesindeki sipariş özelliğini üç uzman "
            "arasında paylaştır. Backend uzmanı yalnızca src/pricing.js "
            "dosyasında calculateOrderTotal(items, discountPercent=0) iş "
            "mantığını tamamlasın: items bir dizi olmalı; price sonlu ve "
            "negatif olmayan sayı, quantity pozitif tam sayı, discountPercent "
            "0-100 arasında sonlu sayı olmalı. Fonksiyon girdileri değiştirmeden "
            "sayısal toplamı döndürmeli, boş sepette 0 vermeli ve ondalıklı "
            "fiyatı tam sayıya yuvarlamamalı. Backend işi "
            "tamamlandıktan sonra frontend uzmanı yalnızca "
            "src/view-model.js dosyasında backend işlevini kullanan "
            "buildOrderSummary(items, discountPercent=0) sunum modelini "
            "tamamlasın. itemCount quantity toplamı olmalı; total backend "
            "sonucu olmalı; label tam olarak '<adet> ürün • <iki ondalıklı, "
            "virgüllü toplam> TRY' biçiminde olmalı. İki üretim görevi "
            "tamamlandıktan sonra QA uzmanı "
            "yalnızca test/edge-cases.test.js dosyasına boş sepet, yüzde 100 "
            "indirim ve geçersiz girdi sınır testlerini yazsın. Mevcut "
            "sözleşme testlerini ve package.json dosyasını değiştirme. Her "
            "uzman kendi hedef dosyasından sorumlu olsun; görevleri backend, "
            "frontend ve QA rollerine ayrı ayrı devret. Son durumda `npm test` "
            "tamamen geçsin. Yeni bağımlılık ekleme ve Git kullanma."
        ),
        seed_files={
            "package.json": """{
  "name": "prometheus-arena-multi-agent-delivery",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test"
  }
}
""",
            "src/pricing.js": """export function calculateOrderTotal(
  items,
  discountPercent = 0,
) {
  return 0;
}
""",
            "src/view-model.js": """import { calculateOrderTotal } from "./pricing.js";

export function buildOrderSummary(items, discountPercent = 0) {
  return {
    itemCount: 0,
    total: calculateOrderTotal(items, discountPercent),
    label: "0 ürün • 0,00 TRY",
  };
}
""",
            "test/pricing.contract.test.js": """import test from "node:test";
import assert from "node:assert/strict";
import { calculateOrderTotal } from "../src/pricing.js";

test("calculates quantities and percentage discount", () => {
  const items = [
    { price: 50, quantity: 2 },
    { price: 20, quantity: 1 },
  ];
  assert.equal(calculateOrderTotal(items, 25), 90);
});

test("does not mutate input items", () => {
  const items = [{ price: 12.5, quantity: 2 }];
  const snapshot = structuredClone(items);
  assert.equal(calculateOrderTotal(items), 25);
  assert.equal(
    calculateOrderTotal([{ price: 7.5, quantity: 1 }]),
    7.5,
  );
  assert.deepEqual(items, snapshot);
});

test("rejects invalid collections, items and discounts", () => {
  assert.throws(() => calculateOrderTotal(null), TypeError);
  assert.throws(
    () => calculateOrderTotal([{ price: -1, quantity: 1 }]),
    TypeError,
  );
  assert.throws(
    () => calculateOrderTotal([{ price: 1, quantity: 0 }]),
    TypeError,
  );
  assert.throws(() => calculateOrderTotal([], 101), RangeError);
});
""",
            "test/view-model.contract.test.js": """import test from "node:test";
import assert from "node:assert/strict";
import { buildOrderSummary } from "../src/view-model.js";

test("builds a deterministic Turkish order summary", () => {
  const summary = buildOrderSummary(
    [
      { price: 50, quantity: 2 },
      { price: 20, quantity: 1 },
    ],
    25,
  );
  assert.deepEqual(summary, {
    itemCount: 3,
    total: 90,
    label: "3 ürün • 90,00 TRY",
  });
});

test("uses singular wording for one item", () => {
  assert.equal(
    buildOrderSummary([{ price: 7.5, quantity: 1 }]).label,
    "1 ürün • 7,50 TRY",
  );
});
""",
        },
        required_paths=(
            "src/pricing.js",
            "src/view-model.js",
            "test/edge-cases.test.js",
        ),
        protected_paths=(
            "package.json",
            "test/pricing.contract.test.js",
            "test/view-model.contract.test.js",
        ),
        verifications=(
            ArenaVerification(name="Tüm Node testleri", preset="npm_test"),
        ),
        max_model_calls=24,
        max_estimated_input_tokens=70_000,
        target_model_calls=12,
        target_total_tokens=36_000,
        minimum_calls_to_start=6,
        timeout_seconds=720,
        required_agents=("backend", "frontend", "qa"),
        minimum_handoffs=6,
    ),
)


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def validate_scenario(scenario: ArenaScenario) -> None:
    if not scenario.id or not scenario.goal.strip():
        raise ValueError("Arena senaryosu kimliği ve hedefi boş olamaz.")
    paths = {
        *scenario.seed_files,
        *scenario.required_paths,
        *scenario.protected_paths,
    }
    invalid = sorted(path for path in paths if not _safe_relative_path(path))
    if invalid:
        raise ValueError(f"Güvensiz Arena yolları: {', '.join(invalid)}")
    missing_protected = sorted(
        set(scenario.protected_paths) - set(scenario.seed_files)
    )
    if missing_protected:
        raise ValueError(
            "Korunan yollar başlangıç dosyası olmalı: "
            + ", ".join(missing_protected)
        )
    if not scenario.verifications:
        raise ValueError("Arena senaryosunda bağımsız doğrulama bulunmalı.")
    if scenario.minimum_calls_to_start > scenario.max_model_calls:
        raise ValueError("Başlangıç çağrı eşiği görev bütçesini aşamaz.")
    if len(set(scenario.required_agents)) != len(scenario.required_agents):
        raise ValueError("Arena zorunlu agent listesi benzersiz olmalı.")
    if any(not agent.strip() for agent in scenario.required_agents):
        raise ValueError("Arena zorunlu agent kimliği boş olamaz.")
    if scenario.minimum_handoffs < 0:
        raise ValueError("Arena minimum handoff sayısı negatif olamaz.")


def list_scenarios() -> tuple[ArenaScenario, ...]:
    for scenario in _SCENARIOS:
        validate_scenario(scenario)
    return _SCENARIOS


def get_scenario(scenario_id: str) -> ArenaScenario:
    normalized = scenario_id.strip().lower()
    for scenario in list_scenarios():
        if scenario.id == normalized:
            return scenario
    available = ", ".join(item.id for item in _SCENARIOS)
    raise KeyError(f"Bilinmeyen Arena senaryosu: {scenario_id}. Mevcut: {available}")
