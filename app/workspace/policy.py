from pathlib import Path
from typing import Iterator

from app.core.exceptions import ToolError


_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".idea",
    ".vscode",
    ".dart_tool",
    ".gradle",
    ".adam",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    "coverage",
    "benchmark",
    "arena",
    "real-world",
}


def _is_excluded_part(part: str) -> bool:
    part_low = part.lower()
    return (
        part_low in _EXCLUDED_PARTS
        or part_low.startswith(".test-tmp")
        or part_low.startswith("pytest-")
        or part_low.startswith("benchmark")
        or part_low.startswith("arena")
        or "benchmark" in part_low
        or part_low.startswith("calculator-")
        or part_low.startswith("context-")
        or part_low.startswith("live_")
    )


_SENSITIVE_DIRECTORY_NAMES = {
    ".ssh",
    ".aws",
    ".gcp",
    ".azure",
}

_SENSITIVE_FILENAMES = {
    ".env",
    "credentials.json",
    "service-account.json",
    "service_account.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "id_rsa",
    "id_ed25519",
}

_SENSITIVE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}

_ALLOWED_ENV_FILENAMES = {
    ".env.example",
}

_SENSITIVE_ACCESS_ERROR = (
    "Hassas ortam, kimlik bilgisi veya anahtar dosyasına erişim engellendi."
)


class WorkspacePolicy:
    def __init__(
        self,
        *,
        root: Path,
        max_file_bytes: int,
        max_search_results: int,
    ) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_file_bytes = max_file_bytes
        self.max_search_results = max_search_results

    def _resolved_candidate(self, path: str | Path) -> Path:
        candidate_input = Path(path)
        if candidate_input.is_absolute():
            return candidate_input.expanduser().resolve(strict=False)
        return (self.root / candidate_input).resolve(strict=False)

    def _relative_parts(self, path: Path) -> tuple[str, ...]:
        try:
            return path.relative_to(self.root).parts
        except ValueError as exc:
            raise ToolError("Workspace dışındaki yollara erişim engellendi.") from exc

    def is_sensitive_path(self, path: str | Path) -> bool:
        """Return True when a workspace path can contain credentials or keys.

        The check is case-insensitive and runs on the resolved path so a symlink
        cannot hide a sensitive target behind a harmless-looking filename.
        """

        candidate = self._resolved_candidate(path)
        try:
            relative_parts = candidate.relative_to(self.root).parts
        except ValueError:
            return False

        lowered_parts = tuple(part.casefold() for part in relative_parts)
        if any(part in _SENSITIVE_DIRECTORY_NAMES for part in lowered_parts):
            return True
        if not lowered_parts:
            return False

        filename = lowered_parts[-1]
        if filename in _ALLOWED_ENV_FILENAMES:
            return False
        if filename in _SENSITIVE_FILENAMES:
            return True
        if filename.startswith(".env."):
            return True
        return Path(filename).suffix.casefold() in _SENSITIVE_SUFFIXES

    def ensure_not_sensitive(self, path: str | Path) -> None:
        candidate = self._resolved_candidate(path)
        self._relative_parts(candidate)
        if self.is_sensitive_path(candidate):
            raise ToolError(_SENSITIVE_ACCESS_ERROR)

    def resolve(
        self,
        relative_path: str | Path = ".",
        *,
        must_exist: bool = False,
        for_write: bool = False,
    ) -> Path:
        value = str(relative_path).strip() or "."
        candidate_input = Path(value)

        if candidate_input.is_absolute():
            raise ToolError("Mutlak yol kullanılamaz; workspace-relative yol ver.")

        candidate = self._resolved_candidate(candidate_input)
        relative_parts = self._relative_parts(candidate)

        if any(_is_excluded_part(part) for part in relative_parts):
            raise ToolError("Korunan veya üretilmiş klasöre erişim engellendi.")

        self.ensure_not_sensitive(candidate)

        if must_exist and not candidate.exists():
            raise ToolError(f"Yol bulunamadı: {value}")

        return candidate

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def ensure_text_file(self, path: Path) -> None:
        resolved = path.resolve(strict=False)
        self._relative_parts(resolved)
        self.ensure_not_sensitive(resolved)
        if not resolved.is_file():
            raise ToolError("İstenen yol bir dosya değil.")
        size = resolved.stat().st_size
        if size > self.max_file_bytes:
            raise ToolError(
                f"Dosya {size} bayt; izin verilen sınır "
                f"{self.max_file_bytes} bayt."
            )
        sample = resolved.read_bytes()[:8_192]
        if b"\x00" in sample:
            raise ToolError("İkili dosya metin aracıyla okunamaz.")

    def iter_files(self, start: Path) -> Iterator[Path]:
        resolved_start = start.resolve(strict=False)
        self._relative_parts(resolved_start)
        if self.is_sensitive_path(resolved_start):
            return

        if resolved_start.is_file():
            self.ensure_text_file(resolved_start)
            yield resolved_start
            return

        for path in resolved_start.rglob("*"):
            try:
                relative_parts = path.relative_to(self.root).parts
            except ValueError:
                continue
            if any(_is_excluded_part(part) for part in relative_parts):
                continue
            if self.is_sensitive_path(path):
                continue
            if path.is_symlink():
                continue
            if path.is_file():
                try:
                    self.ensure_text_file(path)
                except (ToolError, OSError, UnicodeError):
                    continue
                yield path
