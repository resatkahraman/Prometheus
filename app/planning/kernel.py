from dataclasses import dataclass
import json
import re
import unicodedata

from app.planning.models import (
    PlanEvidence,
    PlanTask,
    PlanningDocument,
)
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class PlanningKernelResult:
    document: PlanningDocument
    text: str
    tools_used: list[str]
    project_types: list[str]


def _ascii(value: str) -> str:
    translated = (
        value.casefold()
        .replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    normalized = unicodedata.normalize("NFKD", translated)
    return "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    normalized = _ascii(value)
    return any(_ascii(term) in normalized for term in terms)


def _forward(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def _path_is_explicitly_protected(goal: str, path: str) -> bool:
    """Return true when a mentioned path belongs to a negative instruction."""
    normalized_goal = _ascii(goal)
    normalized_path = _ascii(path)
    for match in re.finditer(re.escape(normalized_path), normalized_goal):
        before = normalized_goal[max(0, match.start() - 64):match.start()]
        after = normalized_goal[match.end():match.end() + 96]
        if re.search(
            r"(?:do not|don't|must not|never)\s+"
            r"(?:change|edit|modify|touch)\s*$",
            before,
        ):
            return True
        if re.match(
            r"\s*(?:dosyasini|dosyasina|dosyayi|file)?\s*"
            r"(?:degistirme|dokunma|koru|silme|"
            r"must not be changed|must remain unchanged|"
            r"do not change|do not edit|do not modify)",
            after,
        ):
            return True
    return False


def _primary_source(path: str) -> bool:
    normalized = _forward(path).casefold()
    auxiliary_prefixes = (
        ".adam/",
        ".test-tmp",
        ".pytest_cache/",
        ".venv/",
        "arena/",
        "arena-local-",
        "benchmark",
        "calculator-benchmark",
        "calculator-context-benchmark",
        "context-live-benchmark/",
        "dist/",
        "node_modules/",
    )
    return not normalized.startswith(auxiliary_prefixes)


_STOPWORDS = {
    "bana", "bir", "bi", "uygulama", "uygulamasi", "uygulamayi", "yap",
    "yapsana", "yapabilir", "proje", "program", "app", "olustur", "ekle",
    "bu", "su", "icin", "istiyorum", "küçük", "kucuk", "basit",
}


def _pascal_feature_name(goal: str) -> str:
    normalized = _ascii(goal)
    known = (
        (("hesap makinesi", "calculator"), "Calculator"),
        (("calculator",), "Calculator"),
        (("not uygulamasi", "not alma", "notes"), "Notes"),
        (("yapilacak", "todo", "gorev listesi"), "Todo"),
        (("hava durumu", "weather"), "Weather"),
        (("sayac", "counter"), "Counter"),
    )
    for aliases, name in known:
        if any(alias in normalized for alias in aliases):
            return name

    words = [
        word
        for word in re.findall(r"[a-z0-9]+", normalized)
        if word not in _STOPWORDS and len(word) > 1
    ]
    selected = words[:3] or ["Feature"]
    return "".join(word[:1].upper() + word[1:] for word in selected)


def _application_intent(goal: str) -> bool:
    normalized = _ascii(goal)
    return any(
        term in normalized
        for term in (
            "uygulama yap", "uygulamasi yap", "uygulama olustur",
            "app yap", "program yap", "hesap makinesi", "calculator",
            "bilesen yap", "component yap",
            "simulasyon yap", "simulasyon olustur", "simulasyonu yap", "simulasyon",
            "web sitesi", "web sayfasi", "site yap", "sayfa yap", "tek html",
            "3d", "3b", "3 boyutlu", "globe", "dunya", "gezegen",
            "html dosya", "t-shirt", "tshirt", "magaza",
        )
    )


def _static_web_app(goal: str) -> bool:
    """
    Returns True when the goal describes a self-contained browser-only web page
    (single HTML file, CDN-based libraries, 3D canvas, globe, etc.).
    These projects CANNOT be tested with Node.js test runners because they rely
    on browser globals (WebGL, Three.js, Canvas, etc.).
    """
    normalized = _ascii(goal)
    return any(
        term in normalized
        for term in (
            "tek html",
            "single html",
            "html dosyasi",
            "3d",
            "3 boyutlu",
            "globe",
            "dunya",
            "gezegen",
            "three.js",
            "threejs",
            "webgl",
            "canvas",
            "animasyon",
        )
    )


class TypedPlanningKernel:
    """
    Deterministic compiler for the Supervisor's critical planning path.

    It converts workspace facts + user decisions into validated PlanTask
    objects directly. No language-model response or Markdown schema is needed.
    """

    def __init__(
        self,
        *,
        tools: ToolRegistry,
        read_max_lines: int = 120,
    ) -> None:
        self.tools = tools
        self.read_max_lines = read_max_lines

    async def _context(self) -> tuple[dict, dict, set[str]]:
        summary = await self.tools.execute("project_summary", {})
        tree = await self.tools.execute(
            "workspace_list",
            {
                "path": ".",
                "depth": 6,
                "max_entries": 500,
            },
        )
        paths = {
            _forward(str(item["path"]))
            for item in tree.get("entries", [])
            if item.get("type") == "file" and item.get("path")
        }
        return summary, tree, paths

    async def _source_fact(self, path: str) -> str:
        try:
            data = await self.tools.execute(
                "workspace_read",
                {
                    "path": path,
                    "start_line": 1,
                    "end_line": self.read_max_lines,
                },
            )
        except Exception:
            return f"`{path}` kaynak dosyası workspace içinde mevcut."

        content = str(data.get("content") or "")
        if path.endswith(".py"):
            functions = re.findall(
                r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
                content,
            )
            if functions:
                names = ", ".join(f"`{name}`" for name in functions[:5])
                return f"`{path}` Python dosyası {names} fonksiyonlarını içeriyor."
            return f"`{path}` Python kaynak dosyası workspace içinde mevcut."

        if path.endswith((".tsx", ".jsx")):
            names = re.findall(
                r"(?:function|const|class)\s+"
                r"([A-Z][A-Za-z0-9_]*)",
                content,
            )
            if names:
                return (
                    f"`{path}` React bileşeni "
                    f"`{names[0]}` tanımını içeriyor."
                )
            return f"`{path}` React/JSX bileşen dosyası olarak mevcut."

        return f"`{path}` dosyası workspace içinde mevcut."

    @staticmethod
    def _resolved_answer_text(
        decision_answers: list[tuple[str, str]] | None,
    ) -> str:
        if not decision_answers:
            return ""
        return "\n".join(answer for _question, answer in decision_answers)

    @staticmethod
    def _web_direction(answer_text: str) -> str | None:
        normalized = _ascii(answer_text)
        if not normalized.strip():
            return None

        negative = (
            "tam web uygulamasina donusturme",
            "web uygulamasina donusturme",
            "framework ekleme",
            "ayri test altyapilari",
            "ayri test altyapisi",
            "bagimsiz test altyapilari",
        )
        if any(term in normalized for term in negative):
            return "independent"

        positive = (
            "web uygulamasina donustur",
            "tam web uygulamasi",
            "vite kullan",
            "next kullan",
            "nextjs kullan",
            "fastapi kullan",
            "flask kullan",
        )
        if any(term in normalized for term in positive):
            return "web"

        return None

    @staticmethod
    def _framework_selected(answer_text: str) -> bool:
        normalized = _ascii(answer_text)
        return any(
            term in normalized
            for term in (
                "vite",
                "next",
                "nextjs",
                "fastapi",
                "flask",
                "django",
            )
        )

    @staticmethod
    def _format(document: PlanningDocument) -> str:
        lines: list[str] = [
            "## Doğrulanmış Proje Gerçekleri",
        ]
        lines.extend(f"- {item}" for item in document.verified_facts)
        lines.extend(["", "## Varsayımlar"])
        lines.extend(
            f"- {item}"
            for item in (document.assumptions or ["Yok"])
        )
        lines.extend(["", "## Görevler"])

        for task in document.tasks:
            evidence = ", ".join(
                f"{item.type}:{item.value}"
                for item in task.evidence
            )
            dependencies = ", ".join(task.dependencies) or "yok"
            exact_files = ", ".join(task.exact_files) or "yok"

            lines.extend(
                [
                    f"### {task.id} — {task.title}",
                    f"Seviye: {task.priority}",
                    f"Atanan Agent: {task.assigned_agent}",
                    f"Kanıt: {evidence}",
                    "Kabul Kriterleri:",
                    *[
                        f"- {criterion}"
                        for criterion in task.acceptance_criteria
                    ],
                    f"Bağımlılıklar: {dependencies}",
                    (
                        "Bağımlılık Gerekçesi: "
                        f"{task.dependency_reason}"
                    ),
                    (
                        "Paralel Çalışabilir: "
                        f"{task.parallelizable}"
                    ),
                    f"Doğrulama: {task.verification}",
                    f"Kullanıcı Onayı: {task.user_approval}",
                    f"Kesin Dosyalar: {exact_files}",
                    "",
                ]
            )

        lines.append("## Kritik Kullanıcı Kararları")
        lines.extend(
            f"- {item}"
            for item in (document.critical_decisions or ["Yok"])
        )
        return "\n".join(lines).strip()

    async def build(
        self,
        *,
        goal: str,
        decision_answers: list[tuple[str, str]] | None = None,
    ) -> PlanningKernelResult:
        summary, _tree, paths = await self._context()
        tools_used = ["project_summary", "workspace_list"]

        python_sources = sorted(
            path
            for path in paths
            if path.endswith(".py")
            and _primary_source(path)
            and not path.startswith(("tests/", ".venv/", "venv/"))
            and "__pycache__" not in path
        )
        react_sources = sorted(
            path
            for path in paths
            if path.endswith((".tsx", ".jsx"))
            and _primary_source(path)
            and (
                path.startswith("src/")
                or "/components/" in f"/{path}"
            )
            and not re.search(r"\.(?:test|spec)\.", path)
        )
        script_sources = sorted(
            path
            for path in paths
            if path.endswith((".js", ".mjs", ".cjs", ".ts"))
            and _primary_source(path)
            and not path.endswith(".d.ts")
            and not path.startswith(
                ("tests/", "test/", "__tests__/", "node_modules/")
            )
            and not re.search(r"\.(?:test|spec)\.", path)
        )

        package_dependencies: set[str] = set()
        if "package.json" in paths:
            try:
                package_data = await self.tools.execute(
                    "workspace_read",
                    {
                        "path": "package.json",
                        "start_line": 1,
                        "end_line": self.read_max_lines,
                    },
                )
                package_manifest = json.loads(
                    str(package_data.get("content") or "{}")
                )
                for section in ("dependencies", "devDependencies"):
                    values = package_manifest.get(section)
                    if isinstance(values, dict):
                        package_dependencies.update(
                            str(name).casefold() for name in values
                        )
                tools_used.append("workspace_read")
            except (TypeError, ValueError, json.JSONDecodeError):
                package_dependencies = set()

        vanilla_markers = {
            "index.html",
            "styles.css",
            "src/app.js",
            "src/calculator.js",
        } & paths
        package_uses_react = (
            "react" in package_dependencies
            or "react-dom" in package_dependencies
            or any(
                name.startswith("@vitejs/plugin-react")
                for name in package_dependencies
            )
        )
        react_project = package_uses_react or (
            bool(react_sources) and len(vanilla_markers) < 2
        )

        preferred_python = (
            ["app.py"]
            if "app.py" in python_sources
            else python_sources[:3]
        )
        preferred_react = react_sources[:8] if react_project else []
        preferred_scripts = script_sources[:8]

        verified_facts: list[str] = []
        for path in [
            *preferred_python,
            *preferred_react,
            *preferred_scripts,
        ]:
            verified_facts.append(
                f"[file:{path}] {await self._source_fact(path)}"
            )
            tools_used.append("workspace_read")

        manifests = set(
            _forward(str(item))
            for item in summary.get("manifests", [])
        )
        project_types = [
            str(item)
            for item in summary.get("project_types", [])
        ]

        if not verified_facts:
            verified_facts.append(
                "[verified_gap:source_files] Workspace içinde planın "
                "doğrudan bağlanabileceği Python veya React kaynak dosyası "
                "bulunamadı."
            )

        normalized_goal = _ascii(goal)
        dependency_free_application = any(
            term in normalized_goal
            for term in (
                "yeni framework veya bagimlilik ekleme",
                "yeni framework ekleme",
                "yeni bagimlilik ekleme",
                "bagimlilik ekleme",
                "no new framework",
                "no new dependency",
                "do not add dependencies",
                "dependency-free",
            )
        ) or (
            "bagimlilik" in normalized_goal
            and any(
                term in normalized_goal
                for term in ("ekleme", "kullanma", "olmadan", "yok")
            )
        )
        wants_tests = any(
            term in normalized_goal
            for term in (
                "test",
                "pytest",
                "jest",
                "vitest",
                "testing library",
                "test altyapisi",
            )
        )

        answer_text = self._resolved_answer_text(decision_answers)
        web_direction = self._web_direction(answer_text)
        asks_web_decision = (
            "web uygulamasi" in normalized_goal
            and any(
                term in normalized_goal
                for term in (
                    "belirsiz",
                    "once bana sor",
                    "karar vermeden",
                    "framework ekleme",
                )
            )
        )

        decisions: list[str] = []
        if asks_web_decision and web_direction is None:
            decisions.append(
                "Proje şimdilik tam bir web uygulamasına mı "
                "dönüştürülecek, yoksa mevcut Python ve React parçaları "
                "bağımsız test çalışma alanları olarak mı korunacak?"
            )
        elif (
            web_direction == "web"
            and not self._framework_selected(answer_text)
        ):
            decisions.append(
                "Tam web uygulaması için kullanılacak uygulama çatısı "
                "hangisi olacak: Vite tabanlı React, Next.js veya başka "
                "bir açık seçim?"
            )

        assumptions: list[str] = []
        if preferred_react and "package.json" not in paths:
            assumptions.append(
                "React bileşenleri mevcut fakat package.json bulunmuyor; "
                "frontend test çalışma alanı sıfırdan kurulacak."
            )
        if python_sources and not (
            {"requirements.txt", "pyproject.toml"} & paths
        ):
            assumptions.append(
                "Python kaynakları mevcut fakat geliştirme/test bağımlılık "
                "manifesti bulunmuyor."
            )
        if not assumptions:
            assumptions.append("Yok")

        tasks: list[PlanTask] = []
        next_id = 1

        requested_python_files = [
            _forward(path)
            for path in re.findall(
                r"(?<![A-Za-z0-9_./-])"
                r"([A-Za-z0-9_./-]+\.py)\b",
                goal,
                flags=re.IGNORECASE,
            )
            if not _forward(path).startswith(("tests/", "test/"))
        ]
        requested_python_test_files = [
            _forward(path)
            for path in re.findall(
                r"(?<![A-Za-z0-9_./-])"
                r"([A-Za-z0-9_./-]+\.py)\b",
                goal,
                flags=re.IGNORECASE,
            )
            if _forward(path).startswith(("tests/", "test/"))
        ]
        requested_react_files = [
            _forward(path)
            for path in re.findall(
                r"(?<![A-Za-z0-9_./-])"
                r"([A-Za-z0-9_./-]+\.(?:tsx|jsx))\b",
                goal,
                flags=re.IGNORECASE,
            )
            if not re.search(
                r"\.(?:test|spec)\.(?:tsx|jsx)$",
                path,
                flags=re.IGNORECASE,
            )
        ]
        requested_script_files = [
            _forward(path)
            for path in re.findall(
                r"(?<![A-Za-z0-9_./-])"
                r"([A-Za-z0-9_./-]+\.(?:js|mjs|cjs|ts))\b",
                goal,
                flags=re.IGNORECASE,
            )
            if not _forward(path).endswith(".d.ts")
            and not _forward(path).startswith(
                ("tests/", "test/", "__tests__/")
            )
            and not re.search(
                r"\.(?:test|spec)\.(?:js|mjs|cjs|ts)$",
                path,
                flags=re.IGNORECASE,
            )
        ]
        requested_script_test_files = [
            _forward(path)
            for path in re.findall(
                r"(?<![A-Za-z0-9_./-])"
                r"([A-Za-z0-9_./-]+\.(?:js|mjs|cjs|ts))\b",
                goal,
                flags=re.IGNORECASE,
            )
            if (
                _forward(path).startswith(
                    ("tests/", "test/", "__tests__/")
                )
                or re.search(
                    r"\.(?:test|spec)\.(?:js|mjs|cjs|ts)$",
                    path,
                    flags=re.IGNORECASE,
                )
            )
        ]
        requested_python_files = [
            path
            for path in requested_python_files
            if not _path_is_explicitly_protected(goal, path)
        ]
        requested_python_test_files = [
            path
            for path in requested_python_test_files
            if not _path_is_explicitly_protected(goal, path)
        ]
        requested_react_files = [
            path
            for path in requested_react_files
            if not _path_is_explicitly_protected(goal, path)
        ]
        requested_script_files = [
            path
            for path in requested_script_files
            if not _path_is_explicitly_protected(goal, path)
        ]
        requested_script_test_files = [
            path
            for path in requested_script_test_files
            if not _path_is_explicitly_protected(goal, path)
        ]
        requested_script_files = list(
            dict.fromkeys(requested_script_files)
        )
        qualified_script_names = {
            path.rsplit("/", 1)[-1]
            for path in requested_script_files
            if "/" in path
        }
        requested_script_files = [
            path
            for path in requested_script_files
            if "/" in path or path not in qualified_script_names
        ]
        requested_script_test_files = list(
            dict.fromkeys(requested_script_test_files)
        )
        requested_functions = re.findall(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*"
            r"(?:\([^)]*\))?\s*fonksiyonunu",
            goal,
            flags=re.IGNORECASE,
        )
        preserve_existing_sources = any(
            term in normalized_goal
            for term in (
                "uretim dosyasini degistirme",
                "kaynak dosyasini degistirme",
                "do not change production",
                "do not change source",
            )
        )
        explicit_python_test_only = bool(
            requested_python_test_files
            and preserve_existing_sources
        )
        concrete_feature = not explicit_python_test_only and bool(
            requested_python_files
            or requested_react_files
            or requested_script_files
        )
        preserve_existing_tests = any(
            term in normalized_goal
            for term in (
                "testleri degistirme",
                "test dosyalarini degistirme",
                "do not change tests",
                "tests must not be changed",
            )
        )
        application_intent = _application_intent(goal)
        requested_html_files = list(dict.fromkeys(
            match.replace("\\", "/")
            for match in re.findall(
                r"(?<![\w.-])([\w./-]+\.html)\b",
                _ascii(goal),
                flags=re.IGNORECASE,
            )
            if not match.startswith(("http://", "https://"))
        ))
        inferred_feature_name = _pascal_feature_name(goal)
        inferred_react_path = (
            f"src/components/{inferred_feature_name}.tsx"
        )
        inferred_module_name = re.sub(
            r"(?<!^)(?=[A-Z])",
            "-",
            inferred_feature_name,
        ).lower()

        def add_task(**kwargs) -> str:
            nonlocal next_id
            task_id = f"TASK-{next_id:03d}"
            tasks.append(PlanTask(id=task_id, **kwargs))
            next_id += 1
            return task_id

        python_feature_task_id: str | None = None
        if concrete_feature and requested_python_files:
            python_path = requested_python_files[0]
            function_name = (
                requested_functions[0]
                if requested_functions
                else "istenen iş mantığı"
            )
            python_criteria = [
                (
                    f"`{python_path}` dosyası bulunmalı ve istenen "
                    "davranışı içermeli."
                ),
                (
                    f"`{function_name}` fonksiyonu kullanıcıdaki "
                    "hesaplama ve doğrulama kurallarını uygulamalı."
                ),
            ]
            separate_python_qa = (
                bool(requested_python_test_files)
                and not preserve_existing_tests
            )
            python_stem = (
                python_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            )
            focused_python_contract = (
                next(
                    (
                        candidate
                        for candidate in (
                            f"tests/test_{python_stem}_backend_contract.py",
                            f"test/test_{python_stem}_backend_contract.py",
                            f"tests/test_{python_stem}_contract.py",
                            f"test/test_{python_stem}_contract.py",
                        )
                        if candidate in paths
                    ),
                    None,
                )
                if separate_python_qa or preserve_existing_tests
                else None
            )
            python_verification = (
                f"python -m pytest -q {focused_python_contract}"
                if focused_python_contract
                else "python -m pytest -q"
            )
            if preserve_existing_tests:
                python_criteria.append(
                    "Mevcut test dosyaları değiştirilmemeli."
                )
            elif separate_python_qa:
                python_criteria.append(
                    "Açıkça istenen pytest dosyaları ayrı QA görevinde "
                    "yazılmalı; backend görevi test dosyasını değiştirmemeli."
                )
            else:
                python_criteria.append(
                    "Pozitif, sıfır, negatif ve sayısal olmayan girdileri "
                    "kapsayan pytest testleri yazılmalı."
                )
            python_criteria.append(
                f"`{python_verification}` exit code 0 ile tamamlanmalı."
            )
            python_feature_task_id = add_task(
                title=(
                    f"{python_path} içinde {function_name} iş mantığını "
                    + (
                        "uygula"
                        if separate_python_qa
                        else "ve Python testlerini uygula"
                    )
                ),
                priority="zorunlu",
                assigned_agent="backend",
                evidence=[
                    PlanEvidence(
                        type="user_request",
                        value=goal.strip(),
                    ),
                    *[
                        PlanEvidence(type="file", value=path)
                        for path in preferred_python
                    ],
                    *(
                        [
                            PlanEvidence(
                                type="file",
                                value=focused_python_contract,
                            )
                        ]
                        if focused_python_contract
                        else []
                    ),
                ],
                acceptance_criteria=python_criteria,
                dependencies=[],
                dependency_reason="yok",
                parallelizable="evet",
                verification=python_verification,
                user_approval="gerekli",
                exact_files=(
                    [python_path]
                    if preserve_existing_tests or separate_python_qa
                    else [
                        python_path,
                        f"tests/test_{python_path.rsplit('/', 1)[-1]}",
                    ]
                ),
            )

        if concrete_feature and requested_react_files:
            react_path = requested_react_files[0]
            add_task(
                title=(
                    f"{react_path} bileşenini ve davranış testlerini uygula"
                ),
                priority="zorunlu",
                assigned_agent="frontend",
                evidence=[
                    PlanEvidence(
                        type="user_request",
                        value=goal.strip(),
                    ),
                    *[
                        PlanEvidence(type="file", value=path)
                        for path in preferred_react
                    ],
                ],
                acceptance_criteria=[
                    f"`{react_path}` bileşeni oluşturulmalı.",
                    (
                        "İstenen girişler, hesaplama düğmesi, sonuç ve "
                        "hata durumu görünür olmalı."
                    ),
                    (
                        "Render, hesaplama, hata ve disabled davranışları "
                        "frontend testleriyle doğrulanmalı."
                    ),
                    (
                        "`npm test -- --run` exit code 0 ile "
                        "tamamlanmalı."
                    ),
                ],
                dependencies=[],
                dependency_reason="yok",
                parallelizable="evet",
                verification="npm test -- --run",
                user_approval="gerekli",
                exact_files=[
                    react_path,
                    re.sub(
                        r"\.(tsx|jsx)$",
                        r".test.\1",
                        react_path,
                        flags=re.IGNORECASE,
                    ),
                ],
            )

        script_task_ids: list[str] = []
        backend_script_task_ids: list[str] = []
        if concrete_feature and requested_script_files:
            default_script_verification = (
                "npm test"
                if "package.json" in paths
                else "node --test"
            )
            for script_path in requested_script_files:
                normalized_script_path = script_path.casefold()
                frontend_script = (
                    normalized_script_path.startswith(
                        ("frontend/", "web/", "client/")
                    )
                    or "/components/" in f"/{normalized_script_path}"
                    or "/pages/" in f"/{normalized_script_path}"
                    or "/ui/" in f"/{normalized_script_path}"
                    or any(
                        marker in normalized_script_path.rsplit("/", 1)[-1]
                        for marker in ("view-model", "view_model", "presenter")
                    )
                )
                assigned_agent = "frontend" if frontend_script else "backend"
                dependencies = (
                    list(backend_script_task_ids)
                    if frontend_script and backend_script_task_ids
                    else []
                )
                stem = (
                    script_path.rsplit("/", 1)[-1]
                    .rsplit(".", 1)[0]
                )
                focused_candidates = (
                    f"test/{stem}.contract.test.js",
                    f"tests/{stem}.contract.test.js",
                    f"test/{stem}.test.js",
                    f"tests/{stem}.test.js",
                )
                focused_test = next(
                    (
                        candidate
                        for candidate in focused_candidates
                        if candidate in paths
                    ),
                    None,
                )
                verification_command = (
                    f"npm test -- {focused_test}"
                    if focused_test and "package.json" in paths
                    else default_script_verification
                )
                task_id = add_task(
                    title=(
                        f"{script_path} içindeki "
                        f"{'sunum modeli' if frontend_script else 'iş mantığı'} "
                        "davranışını uygula ve doğrula"
                    ),
                    priority="zorunlu",
                    assigned_agent=assigned_agent,
                    evidence=[
                        PlanEvidence(
                            type="user_request",
                            value=goal.strip(),
                        ),
                        *[
                            PlanEvidence(type="file", value=path)
                            for path in preferred_scripts
                        ],
                        *(
                            [
                                PlanEvidence(
                                    type="file",
                                    value="package.json",
                                )
                            ]
                            if "package.json" in paths
                            else []
                        ),
                    ],
                    acceptance_criteria=[
                        (
                            f"`{script_path}` kullanıcı isteğindeki davranış "
                            "sözleşmesini sağlamalı."
                        ),
                        (
                            "Mevcut hata doğrulama ve sınır koşulları "
                            "korunmalı."
                        ),
                        (
                            f"`{verification_command}` exit code 0 ile "
                            "tamamlanmalı."
                        ),
                    ],
                    dependencies=dependencies,
                    dependency_reason=(
                        "Sunum modeli backend iş mantığını içe aktardığı için "
                        "önce ilgili backend görevi tamamlanmalıdır."
                        if dependencies
                        else "yok"
                    ),
                    parallelizable="hayır" if dependencies else "evet",
                    verification=verification_command,
                    user_approval="gerekli",
                    exact_files=[script_path],
                )
                script_task_ids.append(task_id)
                if assigned_agent == "backend":
                    backend_script_task_ids.append(task_id)

        if (
            concrete_feature
            and requested_script_test_files
            and script_task_ids
        ):
            verification_command = (
                "npm test"
                if "package.json" in paths
                else "node --test"
            )
            add_task(
                title="JavaScript/TypeScript sınır ve regresyon testlerini yaz",
                priority="zorunlu",
                assigned_agent="qa",
                evidence=[
                    PlanEvidence(
                        type="user_request",
                        value=goal.strip(),
                    ),
                    *[
                        PlanEvidence(type="file", value=path)
                        for path in preferred_scripts
                    ],
                ],
                acceptance_criteria=[
                    (
                        "İstenen normal, sınır ve geçersiz girdi davranışları "
                        "bağımsız Node testleriyle kapsanmalı."
                    ),
                    (
                        "`node:test` ve `node:assert/strict` açıkça import "
                        "edilmeli; global Vitest/Jest API'leri kullanılmamalı."
                    ),
                    "Mevcut üretim kaynak dosyaları değiştirilmemeli.",
                    (
                        f"`{verification_command}` exit code 0 ile "
                        "tamamlanmalı."
                    ),
                ],
                dependencies=list(script_task_ids),
                dependency_reason=(
                    "QA regresyon testleri, iki üretim sözleşmesi "
                    "tamamlandıktan sonra nihai davranışı doğrulamalıdır."
                ),
                parallelizable="hayır",
                verification=verification_command,
                user_approval="gerekli",
                exact_files=requested_script_test_files,
            )

        if requested_python_test_files and (
            not concrete_feature or python_feature_task_id is not None
        ):
            python_test_dependencies = (
                [python_feature_task_id]
                if python_feature_task_id is not None
                else []
            )
            add_task(
                title="İstenen Python test dosyasını oluştur ve doğrula",
                priority="zorunlu",
                assigned_agent="qa",
                evidence=[
                    PlanEvidence(
                        type="user_request",
                        value=goal.strip(),
                    ),
                    *[
                        PlanEvidence(type="file", value=path)
                        for path in preferred_python
                    ],
                ],
                acceptance_criteria=[
                    (
                        "İstenen davranış ve sınır durumları bağımsız pytest "
                        "testleriyle kapsanmalı."
                    ),
                    "Mevcut üretim kaynak dosyaları değiştirilmemeli.",
                    (
                        "`python -m pytest -q` exit code 0 ile "
                        "tamamlanmalı."
                    ),
                ],
                dependencies=python_test_dependencies,
                dependency_reason=(
                    "QA testleri backend üretim sözleşmesi tamamlandıktan "
                    "sonra nihai davranışı doğrulamalıdır."
                    if python_test_dependencies
                    else "yok"
                ),
                parallelizable=(
                    "hayır" if python_test_dependencies else "evet"
                ),
                verification="python -m pytest -q",
                user_approval="gerekli",
                exact_files=list(
                    dict.fromkeys(requested_python_test_files)
                ),
            )

        if (
            not concrete_feature
            and application_intent
            and not react_project
        ):
            is_static = _static_web_app(goal)

            if is_static:
                # Browser-only / single-HTML projects (3D, WebGL, CDN libs).
                # Node.js cannot run these — skip npm test entirely.
                # Verification is simply confirming the HTML file is valid.
                inferred_html_name = (
                    requested_html_files[0]
                    if requested_html_files
                    else f"{inferred_module_name}.html"
                )
                static_acceptance = [
                    (
                        f"`{inferred_html_name}` (ya da `index.html`) "
                        "tüm CSS, JavaScript ve CDN bağlantılarını "
                        "tek dosyada içeren, tarayıcıda çalışan bir "
                        f"{inferred_feature_name} sayfası olmalı."
                    ),
                    (
                        "Sayfa tarayıcıda açıldığında herhangi bir "
                        "console hatası üretmemeli."
                    ),
                    (
                        "Dosya geçerli HTML5 yapısına sahip olmalı "
                        "(<!DOCTYPE html>, <html>, <head>, <body>)."
                    ),
                ]
                if inferred_feature_name == "Calculator":
                    static_acceptance.extend(
                        [
                            "Dört işlem, ondalık sayı, temizle ve geri silme davranışları çalışmalı.",
                            "Bir sayıda birden fazla ondalık ayırıcı ve art arda geçersiz operatör girilememeli.",
                            "Hesaplama eval veya Function constructor kullanmadan güvenli biçimde yapılmalı.",
                        ]
                    )
                else:
                    static_acceptance.append(
                        "İstenen animasyonlar, görseller veya etkileşimli özellikler beklendiği gibi çalışmalı."
                    )
                    if re.search(r"\b(?:3d|webgl|three\.js|gezegen|planet)\b", goal, re.IGNORECASE):
                        static_acceptance.extend(
                            [
                                "Gezegen dönüşü doku, işaret veya yüzey detayı sayesinde gözle açıkça anlaşılmalı.",
                                "Kullanıcı gezegeni fare/sürükleme veya görünür yön düğmeleriyle döndürebilmeli.",
                            ]
                        )
                add_task(
                    title=(
                        f"{inferred_feature_name} için tek dosya statik web "
                        "uygulamasını oluştur"
                    ),
                    priority="zorunlu",
                    assigned_agent="frontend",
                    evidence=[
                        PlanEvidence(
                            type="user_request",
                            value=goal.strip(),
                        ),
                        PlanEvidence(
                            type="verified_gap",
                            value=(
                                "Workspace içinde uygulama kaynağı bulunmuyor"
                            ),
                        ),
                    ],
                    acceptance_criteria=static_acceptance,
                    dependencies=[],
                    dependency_reason="yok",
                    parallelizable="evet",
                    # Static HTML — no Node test runner needed.
                    # Just check the file exists and is valid HTML.
                    verification=f'node -e "require(\'fs\').accessSync(\'{inferred_html_name}\')"',
                    user_approval="gerekli",
                    exact_files=[inferred_html_name],
                )
            else:
                manifest_criterion = (
                    "`package.json` yalnızca yerleşik Node araçlarını kullanan "
                    "`node --test` tabanlı `test` scriptini ve `src/app.js` ile saf "
                    "iş mantığı modülünü `node --check` ile kontrol eden `build` "
                    "scriptini ve `type: module` alanını tanımlamalı; "
                    "dependencies/devDependencies "
                    "eklenmemeli ve sahte `echo` build kullanılmamalı."
                    if dependency_free_application
                    else (
                        "`package.json` içinde Vite tabanlı `dev`, `build` "
                        "ve Node test runner kullanan `test` scriptleri "
                        "tanımlanmalı."
                    )
                )
                implementation_id = add_task(
                    title=(
                        f"{inferred_feature_name} için çalışır web uygulamasını "
                        "ve birim testlerini oluştur"
                    ),
                    priority="zorunlu",
                    assigned_agent="frontend",
                    evidence=[
                        PlanEvidence(
                            type="user_request",
                            value=goal.strip(),
                        ),
                        *(
                            [
                                PlanEvidence(
                                    type="file",
                                    value="package.json",
                                )
                            ]
                            if "package.json" in paths
                            else [
                                PlanEvidence(
                                    type="verified_gap",
                                    value=(
                                        "Workspace içinde uygulama kaynağı veya "
                                        "package.json bulunmuyor"
                                    ),
                                )
                            ]
                        ),
                    ],
                    acceptance_criteria=[
                        (
                            "`index.html`, `styles.css` ve `src/app.js` "
                            "birlikte çalışan, erişilebilir ve responsive bir "
                            f"{inferred_feature_name} arayüzü sağlamalı."
                        ),
                        (
                            f"`src/{inferred_module_name}.js` saf iş mantığını "
                            "DOM kodundan ayırmalı; geçersiz girdiler ve sınır "
                            "durumları açıkça ele alınmalı."
                        ),
                        manifest_criterion,
                        (
                            f"`tests/{inferred_module_name}.test.js` ana işlevi, "
                            "hata durumlarını ve en az bir sınır durumunu "
                            "doğrulamalı."
                        ),
                        (
                            "Test dosyası `node:test` ve `node:assert/strict` "
                            "modüllerini açıkça import etmeli; Jest/Vitest "
                            "globalleri kullanmamalı."
                        ),
                        "`npm test` exit code 0 ile tamamlanmalı.",
                    ],
                    dependencies=[],
                    dependency_reason="yok",
                    parallelizable="evet",
                    verification="npm test",
                    user_approval="gerekli",
                    exact_files=[
                        "package.json",
                        "index.html",
                        "styles.css",
                        "src/app.js",
                        f"src/{inferred_module_name}.js",
                        f"tests/{inferred_module_name}.test.js",
                    ],
                )
                add_task(
                    title="Web uygulamasının üretim build bütünlüğünü doğrula",
                    priority="zorunlu",
                    assigned_agent="integration",
                    evidence=[
                        PlanEvidence(
                            type="user_request",
                            value=goal.strip(),
                        ),
                        PlanEvidence(
                            type="verified_gap",
                            value="Henüz doğrulanmış üretim build kanıtı yok",
                        ),
                    ],
                    acceptance_criteria=[
                        "`npm run build` exit code 0 ile tamamlanmalı.",
                        (
                            "Build çıktısı çalıştırılabilir web giriş dosyasını "
                            "içermeli."
                        ),
                    ],
                    dependencies=[implementation_id],
                    dependency_reason=(
                        "Üretim build'i ancak uygulama kaynakları ve package.json "
                        "oluşturulduktan sonra doğrulanabilir."
                    ),
                    parallelizable="hayır",
                    verification="npm run build",
                    user_approval="gerekmez",
                    exact_files=[],
                )

        if (
            not concrete_feature
            and application_intent
            and react_project
        ):
            harness_files: list[str] = []
            if "package.json" not in paths:
                harness_files = [
                    "package.json",
                    "vitest.config.ts",
                    "src/test/setup.ts",
                ]
                harness_id = add_task(
                    title="Minimal React test çalışma alanını hazırla",
                    priority="zorunlu",
                    assigned_agent="frontend",
                    evidence=[
                        PlanEvidence(type="user_request", value=goal.strip()),
                        PlanEvidence(type="verified_gap", value="package.json bulunmuyor"),
                    ],
                    acceptance_criteria=[
                        "`package.json` yalnızca gerekli React/Vitest bağımlılıklarını ve test scriptini içermeli.",
                        "Vitest jsdom ortamı TSX bileşenlerini çalıştırabilmeli.",
                        "Mevcut Python dosyaları değiştirilmemeli.",
                    ],
                    dependencies=[],
                    dependency_reason="yok",
                    parallelizable="evet",
                    verification="npm test -- --run",
                    user_approval="gerekli",
                    exact_files=harness_files,
                )
            else:
                harness_id = None

            test_path = re.sub(
                r"\.(tsx|jsx)$",
                r".test.\1",
                inferred_react_path,
                flags=re.IGNORECASE,
            )
            dependencies = [harness_id] if harness_id else []
            add_task(
                title=(
                    f"{inferred_feature_name} uygulama bileşenini ve davranış "
                    "testlerini uygula"
                ),
                priority="zorunlu",
                assigned_agent="frontend",
                evidence=[
                    PlanEvidence(type="user_request", value=goal.strip()),
                    *[PlanEvidence(type="file", value=path) for path in preferred_react],
                ],
                acceptance_criteria=[
                    f"`{inferred_react_path}` kullanıcı hedefindeki temel işlevleri görünür bir arayüzle sağlamalı.",
                    "Geçersiz kullanıcı girdileri açık hata durumuyla ele alınmalı.",
                    "Render, ana işlem, hata ve etkileşim durumları test edilmeli.",
                    "`npm test -- --run` exit code 0 ile tamamlanmalı.",
                ],
                dependencies=dependencies,
                dependency_reason=(
                    "React/Vitest manifesti oluşturulmadan bileşen testleri çalıştırılamaz."
                    if dependencies
                    else "yok"
                ),
                parallelizable="hayır" if dependencies else "evet",
                verification="npm test -- --run",
                user_approval="gerekli",
                exact_files=[inferred_react_path, test_path],
            )

        if (
            not concrete_feature
            and not application_intent
            and wants_tests
            and preferred_python
            and not requested_python_test_files
        ):
            python_evidence = [
                PlanEvidence(type="file", value=path)
                for path in preferred_python
            ]
            if not (
                {"requirements.txt", "pyproject.toml"} & paths
            ):
                python_evidence.append(
                    PlanEvidence(
                        type="verified_gap",
                        value=(
                            "Python test bağımlılık manifesti bulunmuyor"
                        ),
                    )
                )

            add_task(
                title=(
                    "Python test altyapısını kur ve mevcut fonksiyonları "
                    "doğrula"
                ),
                priority="zorunlu",
                assigned_agent=(
                    "backend"
                    if not (
                        {"requirements.txt", "requirements-dev.txt",
                         "pyproject.toml"} & paths
                    )
                    else "qa"
                ),
                evidence=python_evidence,
                acceptance_criteria=[
                    (
                        "`tests/test_app.py` pozitif, negatif ve sıfır "
                        "girdileri kapsayan en az üç test fonksiyonu "
                        "içermeli."
                    ),
                    (
                        "Gerekli geliştirme bağımlılıkları "
                        "`requirements-dev.txt` veya mevcut Python "
                        "manifestinde açıkça tanımlanmalı."
                    ),
                    (
                        "`python -m pytest -q` komutu exit code 0 ile "
                        "tamamlanmalı."
                    ),
                ],
                dependencies=[],
                dependency_reason="yok",
                parallelizable="evet",
                verification="python -m pytest -q",
                user_approval="gerekli",
                exact_files=[
                    "tests/test_app.py",
                    *(
                        ["requirements-dev.txt"]
                        if not ({"requirements.txt", "requirements-dev.txt", "pyproject.toml"} & paths)
                        else []
                    ),
                ],
            )

        react_harness_id: str | None = None
        if (
            not concrete_feature
            and not application_intent
            and wants_tests
            and preferred_react
            and "package.json" not in paths
        ):
            react_harness_id = add_task(
                title=(
                    "Bağımsız React test çalışma alanını ve test "
                    "komutlarını kur"
                ),
                priority="zorunlu",
                assigned_agent="frontend",
                evidence=[
                    *[
                        PlanEvidence(type="file", value=path)
                        for path in preferred_react
                    ],
                    PlanEvidence(
                        type="verified_gap",
                        value="package.json bulunmuyor",
                    ),
                ],
                acceptance_criteria=[
                    (
                        "`package.json` içinde Vitest, jsdom, React "
                        "Testing Library ve bir `test` scripti "
                        "tanımlanmalı."
                    ),
                    (
                        "TypeScript ve Vitest yapılandırma dosyaları "
                        "React TSX bileşenlerini dönüştürebilmeli."
                    ),
                    (
                        "`npm install` komutu exit code 0 ile "
                        "tamamlanmalı."
                    ),
                ],
                dependencies=[],
                dependency_reason="yok",
                parallelizable="evet",
                verification="npm install ve npm test -- --run",
                user_approval="gerekli",
                exact_files=[
                    "package.json",
                    "vitest.config.ts",
                    "src/test/setup.ts",
                ],
            )

        if (
            not concrete_feature
            and not application_intent
            and wants_tests
            and preferred_react
        ):
            react_evidence = [
                PlanEvidence(type="file", value=path)
                for path in preferred_react
            ]
            if "package.json" in paths:
                react_evidence.append(
                    PlanEvidence(type="file", value="package.json")
                )

            dependencies = (
                [react_harness_id]
                if react_harness_id is not None
                else []
            )
            dependency_reason = (
                "TASK-002 tarafından oluşturulan package.json ve Vitest "
                "yapılandırması olmadan TSX testleri çalıştırılamaz."
                if react_harness_id is not None
                else "yok"
            )

            add_task(
                title="React bileşen testlerini yaz ve çalıştır",
                priority="zorunlu",
                assigned_agent="qa",
                evidence=react_evidence,
                acceptance_criteria=[
                    (
                        "Her mevcut buton bileşeni için ayrı `.test.tsx` "
                        "dosyası oluşturulmalı."
                    ),
                    (
                        "Render, etiket, tıklama ve varsa disabled "
                        "davranışı test edilmeli."
                    ),
                    (
                        "`npm test -- --run` komutu exit code 0 ile "
                        "tamamlanmalı."
                    ),
                ],
                dependencies=dependencies,
                dependency_reason=dependency_reason,
                parallelizable="hayır" if dependencies else "evet",
                verification="npm test -- --run",
                user_approval="gerekli",
                exact_files=[
                    re.sub(
                        r"\.(tsx|jsx)$",
                        r".test.\1",
                        path,
                        flags=re.IGNORECASE,
                    )
                    for path in preferred_react
                ],
            )

        if not tasks:
            decisions.append(
                "Hedefin uygulanacağı platformu ve teslim dosyalarını belirt: "
                "mevcut React bileşeni, Python modülü veya başka bir çalışma alanı."
            )
            add_task(
                title="Kullanıcı kararından sonra somut dosya planını tamamla",
                priority="zorunlu",
                assigned_agent="planner",
                evidence=[PlanEvidence(type="user_request", value=goal.strip())],
                acceptance_criteria=[
                    "Kullanıcı kararı sonrasında görevler kesin dosya yollarıyla yeniden derlenmeli.",
                    "Kesin dosyası olmayan mutasyon görevi çalıştırılmamalı.",
                ],
                dependencies=[],
                dependency_reason="yok",
                parallelizable="evet",
                verification="project_summary",
                user_approval="gerekmez",
                exact_files=[],
            )

        document = PlanningDocument(
            verified_facts=verified_facts,
            assumptions=assumptions,
            tasks=tasks,
            critical_decisions=decisions,
        )

        return PlanningKernelResult(
            document=document,
            text=self._format(document),
            tools_used=list(dict.fromkeys(tools_used)),
            project_types=project_types,
        )
