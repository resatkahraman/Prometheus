from collections.abc import Iterable

from app.agents.access import AgentAccessController
from app.agents.models import AgentProfile


READ = [
    "project_summary",
    "workspace_list",
    "workspace_read",
    "workspace_search",
    "git_status",
    "git_diff",
]
COMMON = [
    "calculator",
    "current_datetime",
    "text_stats",
    "symbolic_math",
]
WORK = [
    *READ,
    *COMMON,
    "workspace_write",
    "safe_terminal",
]


class AgentRegistry:
    def __init__(
        self,
        *,
        profiles: Iterable[AgentProfile],
        available_tools: Iterable[str],
    ) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        self._tools = set(available_tools)
        self.access = AgentAccessController()

        for profile in profiles:
            self.register(profile)

        if "worker" not in self._profiles:
            raise ValueError("'worker' profili zorunlu")

    def register(self, profile: AgentProfile) -> None:
        if profile.id in self._profiles:
            raise ValueError(f"Agent zaten kayıtlı: {profile.id}")

        unknown = sorted(set(profile.allowed_tools) - self._tools)
        if unknown:
            raise ValueError(
                f"{profile.id} bilinmeyen araçlar: {', '.join(unknown)}"
            )

        if profile.read_only and profile.write_paths:
            raise ValueError(
                f"{profile.id} read-only ama write_paths içeriyor"
            )

        self._profiles[profile.id] = profile

    def get(self, agent_id: str) -> AgentProfile:
        profile = self._profiles.get(agent_id.strip().lower())
        if not profile:
            raise ValueError(f"Bilinmeyen agent profili: {agent_id}")
        return profile

    def all(self) -> list[AgentProfile]:
        return list(self._profiles.values())

    def ids(self) -> list[str]:
        return list(self._profiles)

    def authorize(
        self,
        *,
        profile: AgentProfile,
        tool_name: str,
        arguments: dict,
    ) -> None:
        self.access.authorize(
            profile=profile,
            tool_name=tool_name,
            arguments=arguments,
        )


def profile(
    *,
    id: str,
    name: str,
    short: str,
    description: str,
    mission: list[str],
    routes: list[str],
    tools: list[str],
    write: list[str] | None = None,
    read_only: bool = False,
    steps: int = 12,
    calls: int = 16,
    task_type: str | None = None,
    auto_context: bool = False,
    contract: list[str] | None = None,
    instructions: list[str] | None = None,
) -> AgentProfile:
    return AgentProfile(
        id=id,
        name=name,
        short_name=short,
        description=description,
        mission=mission,
        preferred_routes=routes,
        allowed_tools=tools,
        read_paths=["**"],
        write_paths=write or [],
        read_only=read_only,
        max_steps=steps,
        max_model_calls=calls,
        task_type_override=task_type,
        auto_context=auto_context,
        output_contract=contract or [],
        instructions=instructions or [],
    )


def build_default_agent_registry(
    available_tools: Iterable[str],
) -> AgentRegistry:
    profiles = [
        profile(
            id="worker",
            name="General Worker",
            short="Worker",
            description="Genel proje geliştirme workerı.",
            mission=[
                "Gerçek proje bağlamıyla görevi tamamla.",
                "Değişiklikleri test ve diff ile doğrula.",
            ],
            routes=["groq_strong", "github", "gemini", "groq_fast"],
            tools=WORK,
            write=["**"],
            steps=12,
            calls=16,
            contract=[
                "İncelenen veya değiştirilen dosyalar.",
                "Gerçek test ve araç sonuçları.",
                "Kalan sorunlar veya doğrulanamayan noktalar.",
            ],
        ),
        profile(
            id="planner",
            name="Product Planner",
            short="Planner",
            description=(
                "Kanıtlı, atanabilir ve bağımlılıkları doğrulanabilir "
                "görev grafiği oluşturan salt okunur planlayıcı."
            ),
            mission=[
                "Hedefi doğrulanmış gerçekler ve açık varsayımlara ayır.",
                "Her görevi tek bir uzman agente atanabilecek kapsamda tanımla.",
                "Bağımlılıkları yalnızca teknik zorunluluk varsa kur.",
                "Bağımsız işleri paralel çalışabilir olarak işaretle.",
            ],
            routes=["groq_strong", "gemini", "github", "groq_fast"],
            tools=[*READ, "calculator", "current_datetime", "text_stats"],
            read_only=True,
            steps=12,
            calls=12,
            task_type="reasoning",
            auto_context=True,
            contract=[
                "Doğrulanmış Proje Gerçekleri bölümü.",
                "Varsayımlar bölümü.",
                "Makine tarafından ayrıştırılabilir TASK blokları.",
                "Her görevde seviye, agent, kanıt ve kabul kriterleri.",
                "Her görevde bağımlılık, teknik gerekçe ve paralellik bilgisi.",
                "Her görevde doğrulama ve kullanıcı onayı bilgisi.",
                "Kritik Kullanıcı Kararları bölümü.",
            ],
            instructions=[
                "Dosya değiştirme.",
                "Markdown tablosu kullanma; her alanı ayrı satırda yaz.",
                "Alan adlarını değiştirme veya kısaltma.",
                "Web frontend görevi ise son göreve 'Tarayıcıda test et' adımı ekle.",
                "Basit HTML/JS projeleri tek dosya olarak planla.",
                "Aşağıdaki plan biçimini harfiyen kullan:",
                "## Doğrulanmış Proje Gerçekleri",
                "- [file:app.py] Gerçek ve kanıtlı açıklama",
                "## Varsayımlar",
                "- Varsayım yoksa 'Yok' yaz.",
                "## Görevler",
                "### TASK-001 — Kısa görev başlığı",
                "Seviye: zorunlu | önerilen | opsiyonel",
                "Atanan Agent: worker|frontend|backend|database|qa|architect|reviewer|integration|calculation",
                "Kanıt: Bir veya daha fazla kanıt; örnek: file:app.py, file:src/App.tsx",
                "Kabul Kriterleri:",
                "- Ölçülebilir kriter",
                "Bağımlılıklar: yok | TASK-001, TASK-002",
                "Bağımlılık Gerekçesi: yok | teknik ve somut gerekçe",
                "Paralel Çalışabilir: evet | hayır",
                "Doğrulama: gerçek komut, test veya inceleme yöntemi",
                "Kullanıcı Onayı: gerekmez | gerekli",
                "Kesin Dosyalar: yok | path/a, path/b",
                "## Kritik Kullanıcı Kararları",
                "- Karar yoksa 'Yok' yaz.",
                "Birden fazla kanıtı tek Kanıt satırında her birinin türünü tekrar ederek yaz.",
                "Doğru: file:app.py, file:src/App.tsx",
                "Yanlış: file:app.py, src/App.tsx",
                "Yalnızca varsayıma dayalı görev zorunlu olamaz.",
                "Silme görevi kesin dosya listesi ve kullanıcı onayı olmadan yazılamaz.",
                "Aynı sırada görünmesi görevler arasında bağımlılık olduğu anlamına gelmez.",
                "Kabul kriterinde 'uygun', 'düzenli' veya 'başarılı şekilde' gibi ölçülemeyen ifadeleri tek başına kullanma.",
            ],
        ),
        profile(
            id="architect",
            name="Software Architect",
            short="Architect",
            description=(
                "Mevcut sistemi, riskleri, modül sınırlarını ve hedef "
                "mimariyi inceleyen salt okunur uzman."
            ),
            mission=[
                "Mevcut mimariyi gerçek dosyalardan çıkar.",
                "Sürdürülebilir hedef yapı, sözleşme ve veri akışı üret.",
                "Riskleri ve geçiş planını önceliklendir.",
            ],
            routes=["gemini", "groq_strong", "github", "groq_fast"],
            tools=[*READ, *COMMON],
            read_only=True,
            steps=12,
            calls=12,
            task_type="reasoning",
            auto_context=True,
            contract=[
                "Mevcut durum ve kullanılan teknoloji.",
                "Somut mimari riskler.",
                "Önerilen hedef mimari ve modül sorumlulukları.",
                "Arayüz veya veri sözleşmeleri.",
                "Uygulama sırası ve doğrulama planı.",
            ],
            instructions=[
                "Dosya değiştirme.",
                "Aynı başlığı veya riski tekrar etme.",
                "Görmediğin dosyayı veya bağımlılığı varmış gibi anlatma.",
            ],
        ),
        profile(
            id="frontend",
            name="Frontend Engineer",
            short="Frontend",
            description="Web/Flutter arayüz ve istemci entegrasyonu uzmanı.",
            mission=[
                "Arayüz, component ve state kodunu geliştir.",
                "Responsive ve test edilebilir davranış üret.",
            ],
            routes=["github", "groq_strong", "gemini", "groq_fast"],
            tools=WORK,
            write=[
                "frontend/**",
                "web/**",
                "client/**",
                "lib/**",
                "src/components/**",
                "src/pages/**",
                "src/screens/**",
                "src/styles/**",
                "src/assets/**",
                "test/**",
                "tests/**",
                "integration_test/**",
                "package.json",
                "pubspec.yaml",
            ],
            steps=14,
            calls=16,
            task_type="coding",
            auto_context=True,
            contract=[
                "Değişen UI dosyaları.",
                "API sözleşmeleri ve varsayımlar.",
                "Responsive/hata durumu davranışları.",
                "Frontend analiz veya test sonuçları.",
            ],
            instructions=[
                "Backend veya veritabanı kodunu değiştirme.",
                "Dosya yazdıysan final cevapta 'Doğrulama Durumu:' alanı ver.",
                "Test çalışmadıysa açıkça 'test edilmedi/doğrulanmadı' yaz.",
                "Web projesi ise docs/WEB_DEPLOYMENT_GUIDE.md'yi oku ve uygula.",
                "Basit HTML projelerde (hesap makinesi, form) tek dosya kullan.",
                "ES modules + file:// = CORS hatası. Basit projeler inline JS kullan.",
                "Node testleri geçti != tarayıcıda çalışıyor. Mutlaka tarayıcı testi yap.",
            ],
        ),
        profile(
            id="backend",
            name="Backend Engineer",
            short="Backend",
            description="API, servis ve iş mantığı uzmanı.",
            mission=[
                "API ve iş mantığını geliştir.",
                "Güvenlik ve hata durumlarını test et.",
            ],
            routes=["github", "groq_strong", "gemini", "groq_fast"],
            tools=WORK,
            write=[
                "backend/**",
                "server/**",
                "api/**",
                "app/**",
                "src/**",
                "tests/**",
                "test/**",
                "requirements.txt",
                "requirements-dev.txt",
                "pyproject.toml",
                "package.json",
                "Cargo.toml",
            ],
            steps=15,
            calls=17,
            task_type="coding",
            auto_context=True,
            contract=[
                "Endpoint veya servis değişiklikleri.",
                "Request/response sözleşmeleri.",
                "Hata ve güvenlik davranışları.",
                "Backend test sonuçları.",
            ],
            instructions=["UI dosyalarını değiştirme."],
        ),
        profile(
            id="database",
            name="Database Engineer",
            short="Database",
            description="Şema, model, migration ve veri bütünlüğü uzmanı.",
            mission=[
                "Şema ve migration tasarla.",
                "Veri kaybı, indeks ve rollback risklerini doğrula.",
            ],
            routes=["groq_strong", "github", "gemini", "groq_fast"],
            tools=WORK,
            write=[
                "database/**",
                "db/**",
                "migrations/**",
                "prisma/**",
                "alembic/**",
                "app/models/**",
                "app/db/**",
                "backend/models/**",
                "backend/db/**",
                "tests/**",
                "test/**",
                "*.sql",
                "schema.*",
            ],
            steps=13,
            calls=15,
            task_type="coding",
            contract=[
                "Şema veya migration değişiklikleri.",
                "Rollback ve veri kaybı riski.",
                "İndeks ve bütünlük kararları.",
                "Doğrulama sonuçları.",
            ],
        ),
        profile(
            id="qa",
            name="QA and Test Engineer",
            short="QA",
            description="Test senaryosu, regresyon ve hata kanıtı uzmanı.",
            mission=[
                "Kabul kriterlerinden testler çıkar.",
                "Gerçek test sonuçlarını yeniden üretilebilir raporla.",
            ],
            routes=["github", "groq_strong", "gemini", "groq_fast"],
            tools=WORK,
            write=[
                "tests/**",
                "test/**",
                "integration_test/**",
                "e2e/**",
                "spec/**",
                "__tests__/**",
                "pytest.ini",
                "vitest.config.*",
                "jest.config.*",
            ],
            steps=14,
            calls=16,
            task_type="coding",
            contract=[
                "Test senaryoları.",
                "Çalıştırılan komutlar ve exit code.",
                "Başarılı/başarısız test sonuçları.",
                "Başarısızlık kanıtları ve yeniden çalışma görevi.",
            ],
            instructions=[
                "Üretim kodunu doğrudan düzeltme.",
                "pytest.ini bir bağımlılık manifesti değildir; eksik "
                "requirements-dev.txt yerine pytest.ini oluşturma.",
                "Aynı test komutunu başarılı kanıt mevcutken gereksiz "
                "biçimde yeniden çalıştırma.",
            ],
        ),
        profile(
            id="reviewer",
            name="Independent Reviewer",
            short="Reviewer",
            description=(
                "Diff, gereksinim ve testleri bağımsız denetleyen "
                "salt okunur reviewer."
            ),
            mission=[
                "Gereksinimleri dosya, diff ve test kanıtıyla doğrula.",
                "Kabul/ret kararı ve yeniden çalışma görevleri üret.",
            ],
            routes=["gemini", "groq_strong", "github", "groq_fast"],
            tools=[*READ, *COMMON, "safe_terminal"],
            read_only=True,
            steps=13,
            calls=14,
            task_type="reasoning",
            auto_context=True,
            contract=[
                "Açık KABUL veya RET kararı.",
                "Kararı destekleyen dosya/diff/test kanıtları.",
                "Önem sırasına göre sorunlar.",
                "İlgili agente verilecek yeniden çalışma görevleri.",
            ],
            instructions=[
                "Dosya değiştirme.",
                "Agent açıklamasını tek başına kanıt sayma.",
            ],
        ),
        profile(
            id="integration",
            name="Integration Engineer",
            short="Integration",
            description=(
                "Bileşenleri birleştirip build/test bütünlüğünü sağlayan worker."
            ),
            mission=[
                "Bileşen sözleşmelerini doğrula.",
                "Entegrasyon, build ve test sonucunu kanıtla.",
            ],
            routes=["github", "groq_strong", "gemini", "groq_fast"],
            tools=WORK,
            write=["**"],
            steps=16,
            calls=18,
            task_type="coding",
            contract=[
                "Birleştirilen bileşenler.",
                "Çözülen uyuşmazlıklar.",
                "Build/test sonuçları.",
                "Teslimi engelleyen kalan sorunlar.",
            ],
        ),
        profile(
            id="calculation",
            name="Engineering Calculation Specialist",
            short="Calculation",
            description=(
                "Mühendislik hesabını deterministik araçlarla yapan "
                "salt okunur uzman."
            ),
            mission=[
                "Değişken ve birimleri belirle.",
                "Hesabı calculator veya SymPy ile yap ve doğrula.",
            ],
            routes=["groq_strong", "gemini", "github", "groq_fast"],
            tools=[
                "calculator",
                "symbolic_math",
                "text_stats",
                "current_datetime",
                "project_summary",
                "workspace_list",
                "workspace_read",
                "workspace_search",
            ],
            read_only=True,
            steps=8,
            calls=8,
            task_type="reasoning",
            contract=[
                "Kullanılan işlem veya formül.",
                "Araçla hesaplanan gerçek sonuç.",
                "Varsayımlar, birimler ve sınırlamalar.",
            ],
            instructions=[
                "Sayısal sonucu yalnızca model tahminiyle üretme.",
                "Açık sembolik işlem araçla çözülebiliyorsa modeli gereksiz kullanma.",
            ],
        ),
    ]

    return AgentRegistry(
        profiles=profiles,
        available_tools=available_tools,
    )
