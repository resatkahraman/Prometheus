# Prometheus v0.8.0 — Experience Kernel & Forge

Bu sürüm, v0.7.22'nin kesilmeye dayanıklı dosya üretimini korurken Prometheus'a
doğrulanmış deneyim belleği, sabit bütçeli proje yönlendirmesi, yerel hibrit RAG,
güvenli yama üretimi, gölge rota öğrenimi ve kontrollü self-improvement
laboratuvarı ekler.

## Prometheus Forge kullanıcı arayüzü

Sunucuyu başlatıp `http://127.0.0.1:8000/lab` adresini aç:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Prometheus varsayılan olarak yalnızca loopback istemcilerinden gelen ve
`localhost`, `127.0.0.1` veya `::1` hedefli HTTP isteklerini kabul eder.
Uvicorn yanlışlıkla `--host 0.0.0.0` ile başlatılsa bile uzak istemciler
uygulama katmanında `403` yanıtıyla engellenir. Ayrıca yabancı `Host`
başlıkları reddedilerek yerel servise yönelik DNS-rebinding girişimleri
sınırlandırılır.

`HTTP_REMOTE_ACCESS_ENABLED=true` uzak erişim modunu açar; bu modda bütün
HTTP rotaları için en az 32 karakterlik `HTTP_AUTH_TOKEN` zorunludur. Token
yoksa veya kısaysa uygulama yapılandırması reddedilir. Uzak erişim modu açıkken
localhost istekleri de kimlik doğrulaması olmadan kabul edilmez.

Güçlü token üretmek için:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`.env` örneği:

```env
HTTP_REMOTE_ACCESS_ENABLED=true
HTTP_AUTH_TOKEN=buraya-uretilen-en-az-32-karakterlik-token
```

Tarayıcı arayüzü HTTP Basic Auth kullanır. Kullanıcı adı `prometheus`, parola
`HTTP_AUTH_TOKEN` değeridir. API istemcileri aynı tokenı Bearer olarak gönderebilir:

```powershell
curl.exe -H "Authorization: Bearer $env:PROMETHEUS_TOKEN" http://127.0.0.1:8000/v1/health
```

Uzak erişimde sunucuyu bilinçli olarak ağ arayüzüne bağla:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Bütün `POST`, `PUT`, `PATCH` ve `DELETE` istekleri ayrıca
`X-Prometheus-CSRF: 1` başlığını taşımalıdır. Prometheus tarayıcı arayüzleri bu
başlığı otomatik ekler. Yerel veya uzak API istemcileri durum değiştiren çağrılarda
başlığı açıkça göndermelidir:

```powershell
curl.exe -X DELETE `
  -H "Authorization: Bearer $env:PROMETHEUS_TOKEN" `
  -H "X-Prometheus-CSRF: 1" `
  http://127.0.0.1:8000/v1/cache
```

Bu sabit değer bir parola değildir. Özel HTTP başlığı, yabancı bir web sitesindeki
basit formun tarayıcıdaki Basic Auth oturumunu kullanarak Prometheus üzerinde işlem
yapmasını engeller; sunucu ayrıca cross-origin erişim için CORS izni vermez.

Basic/Bearer kimlik bilgileri düz HTTP üzerinde şifrelenmez. Uzak erişimi yalnızca
güvenilir özel ağ veya VPN içinde kullan; internet yayını için TLS reverse proxy
olmadan sistemi açma. Tokenı URL query parametresine koyma, loglama veya kaynak
kontrolüne ekleme.

## Trusted otonomi güvenlik kapısı

`autonomy_mode=trusted`, dosya yazma gibi düşük riskli araçların görev başına
onay beklemeden çalışmasına izin verebildiği için varsayılan olarak sunucu
tarafında kapalıdır. İstemcinin yalnızca JSON gövdesinde `trusted` göndermesi
yeterli değildir. Açık ve bilinçli opt-in gerekir:

```env
SUPERVISOR_DEFAULT_AUTONOMY_MODE=task
SUPERVISOR_TRUSTED_AUTONOMY_ENABLED=false
```

Trusted modu gerçekten kullanmak için:

```env
SUPERVISOR_TRUSTED_AUTONOMY_ENABLED=true
```

Varsayılan modu da trusted yapmak istenirse iki ayar birlikte verilmelidir:

```env
SUPERVISOR_TRUSTED_AUTONOMY_ENABLED=true
SUPERVISOR_DEFAULT_AUTONOMY_MODE=trusted
```

Opt-in kapalıyken yeni trusted komutlar `403` ile reddedilir. Daha önce kalıcı
depoya yazılmış trusted komutlar da düşük riskli araçları otomatik çalıştıramaz;
onay akışına geri düşer. Yüksek riskli araçlar trusted mod açık olsa bile
otomatik çalıştırılmaz. Uzak HTTP erişiminde trusted komut gönderebilmek için
mevcut Basic/Bearer kimlik doğrulaması ve CSRF başlığı da zorunludur.

Arayüzde:

- gerçek Supervisor görevleri başlatılabilir ve önemli işlemler onaylanabilir,
- PEEK/TLB benzeri sabit bütçeli deneyim kapsülü sorgulanabilir,
- SQLite + `qwen3-embedding:0.6b` hibrit RAG dizini yenilenebilir,
- Forge adayları 40 vakalık görünür/gizli/adversarial Arena'da ölçülebilir,
- yalnızca başarılı strateji/prompt adayları açık kullanıcı onayıyla terfi
  ettirilebilir ve geri alınabilir.

Kaynak kodu değiştiren Forge adayları canlı sisteme otomatik uygulanmaz.
Yalnızca allowlist içindeki gölge kopyada hash ve statik sözdizimi kontrolünden
geçebilir; çalıştırma ve otomatik terfi kapalıdır.

Yerel embedding kurulumu:

```powershell
ollama pull qwen3-embedding:0.6b
```

Yeni Improvement Arena:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_improvement_benchmark
```

## Yeni tek-dosya protokolü

Focused source generation no longer asks the provider to escape an entire
TypeScript/Python file inside JSON. The provider returns:

```text
<<<ADAM_FILE path="src/components/Calculator.tsx">>>
complete raw source
<<<END_ADAM_FILE>>>
```

The closing marker is mandatory. A token-limit truncation can therefore never
be applied as a partial file.

## Output budget

Normal agent turns keep their small budget. A focused exact-file generation
gets a separate 8192-token budget, configurable with:

```env
SUPERVISOR_FOCUSED_FILE_OUTPUT_TOKENS=8192
```

## Loop guard

A focused protocol failure becomes `focused_protocol_failed` and is blocked by
state signature. It is not restarted repeatedly. Bağlam seçici veya dosya
protokolü revizyonu ilerlediğinde
`focused_generation_revision_advanced` oluşturulur ve yeni revizyonda yalnızca
bir güvenli yeniden denemeye izin verilir.

## Yerel proje belleği ve bağlam bütçesi

Prometheus, Python ile birlikte gelen SQLite desteğini kullanır; ayrı bir SQLite
kurulumu gerekmez. `.adam/project_memory.db` yalnızca dosya hash'lerini,
deterministik kod özetlerini ve bağlam ölçümlerini saklar. Tam kaynak dosyaları,
promptlar ve API anahtarları bu belleğe yazılmaz.

Her model çağrısında bütün görev dosyaları yeniden gönderilmez. Hedef dosya ve
en ilgili bir komşu dosya tam içerikle, diğer dosyalar ise yerel sembol özetiyle
verilir. Eski araç cevapları kısa işlem makbuzlarına dönüştürülür ve aktif
bağlam varsayılan olarak 24.000 karakterle sınırlandırılır.

Yeni API kullanım satırları gerçek prompt karakter sayısını, yaklaşık token
ön-tahminini, misyon kimliğini ve görev kimliğini içerir. Böylece kullanım
raporu artık zaman aralığı tahmini yerine doğrudan göreve göre çıkarılabilir.

## Context Compiler V1 ve yerel RAG

`CONTEXT_COMPILER_MODE=active` varsayılandır. Derleyici daha küçük bir
`ADAM_CONTEXT_CAPSULE_V1` adayı oluşturur; aday zorunlu kanıtı eksiksiz taşıyor
ve mevcut bağlamdan gerçekten küçükse modele gönderilir. `shadow` seçeneği aynı
adayı yalnızca ölçer ve gerçek model girdisini değiştirmez.
Zorunlu hedef kaynak, doğrudan import veya doğrulama sözleşmesi bütçeye tam
sığmazsa aday `eligible=false` ve `fallback_required=true` olur; görünen token
tasarrufu kalite kazanımı sayılmaz.

Yerel RAG katmanı internet veya embedding API'si kullanmaz. SQLite içindeki
yalnızca `verified` durumundaki sembol, bağımlılık, test ve kullanıcı-kararı
kanıtlarını görev sözcükleriyle ve gerçek dosya komşuluğuyla sıralar. Her kaynak
hash'e bağlıdır; dosya değiştiğinde eski kanıt `stale` olur ve kapsül cache
anahtarı otomatik değişir. Tam kaynak/prompt veritabanına kaydedilmez.

Arena sonuçlarındaki `context_compiler` alanı gölge çalışma sayısını, güvenli
aday oranını, gerçekten daha küçük olan aday oranını, hash-cache isabetlerini
ve yalnızca kalite kapısından geçen tahmini karakter/token tasarrufunu raporlar.
Kapsül mevcut bağlamdan büyükse otomatik olarak `bypassed` sayılır. Aktif moda
geçiş ancak aynı bağımsız
testler ve teslim kalitesi korunarak tekrarlanan Arena A/B ölçümlerinden sonra
yapılacaktır.

```env
CONTEXT_COMPILER_MODE=active
CONTEXT_COMPILER_SHADOW_BUDGET_CHARS=8000
CONTEXT_RAG_ENABLED=true
CONTEXT_RAG_MAX_CARDS=32
CONTEXT_RAG_SCAN_LIMIT=1000
```

## Doğrulamalı yerel Qwen rotası

Prometheus, Ollama üzerindeki `qwen3:4b-instruct-2507-q4_K_M` modelini düşük riskli,
tek dosyalı ve çalıştırılabilir test kapısı bulunan görevlerde bir kez
deneyebilir. Yerel çağrı dış API misyon bütçesini tüketmez. Çıktı protokolü
bozulursa veya sonraki test başarısız olursa aynı görevde yerel model yeniden
denenmez; mevcut ücretsiz API rotalarına kanıtlı fallback yapılır.

Güvenlik, kimlik doğrulama, ödeme, migration ve production/deployment
görevleri; uzun bağlamlar ve çalıştırılabilir doğrulaması olmayan işler yerel
ilk denemeyi otomatik atlar. Yerel model nihai doğruluk otoritesi değildir.

Windows kurulumu:

```powershell
winget install --id Ollama.Ollama --exact
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

Uzak API harcamadan yerel rotayı tek başına doğrulamak için:

```powershell
.\.venv\Scripts\python.exe scripts\run_prometheus_arena.py --scenario js_bugfix --live --local-only
```

```env
LOCAL_MODEL_ENABLED=true
OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
OLLAMA_CONTEXT_TOKENS=4096
OLLAMA_MAX_OUTPUT_TOKENS=1000
LOCAL_MODEL_MAX_INPUT_CHARS=12000
LOCAL_MODEL_MAX_ATTEMPTS_PER_TASK=1
```

Arena kullanım raporu `local_calls/local_tokens` ile
`remote_calls/remote_tokens` alanlarını ayrı verir. Böylece yerel modelin
gerçek API tasarrufu toplam model tokenından bağımsız ölçülür.

## Free-First Budget Governor

`FREE_ONLY_MODE=true` ücretli rotalar için ana kilittir. Gelecekte ücretli bir
sağlayıcı ve API anahtarı tanımlansa bile kullanıcı bu kilidi bilinçli olarak
kapatmadan, `PAID_MODELS_ENABLED=true` yapmadan ve pozitif aylık bütçe
vermeden ücretli çağrı çalışmaz.

Her Supervisor misyonunun bütün agent oturumları arasında paylaşılan kalıcı
bütçesi vardır. Varsayılan tavan 24 dış model çağrısı ve 60.000 tahmini giriş
tokenıdır. Sayaç `operations.db` içinde misyon kimliğiyle tutulduğu için süreç
yeniden başlasa da sıfırlanmaz. Tavan dolduğunda Prometheus ücretli modele geçmez;
misyonu açık bir bütçe hatasıyla durdurur.

Ücretsiz bir rotanın günlük kotası son `%10` dilime girdiğinde dinamik puanlama
o rotaya artan kota-koruma cezası uygular ve uygun başka ücretsiz rotayı öne
alır. Diğer rotalar da kullanılamıyorsa kalan ücretsiz rota tamamen kapatılmaz.
Free-only modunda sağlayıcı içi retry sayısı ayrıca en fazla 1 ile
sınırlandırılır.

HTTP istemcisinin okuma timeout'u yalnızca bağlantının hareketsiz kaldığı süreyi
ölçtüğü için canlı bir bağlantı eskiden Supervisor görev süresinin tamamını
tüketebiliyordu. `PROVIDER_CALL_WALL_TIMEOUT_SECONDS=90` artık dış çağrıya toplam
duvar saati tavanı uygular. Kısa yanıtlar çıktı bütçesine göre yaklaşık 25-35
saniyede güvenli fallback'e geçerken, büyük tek-dosya üretimleri yapılandırılmış
90 saniyelik tavana kadar süre alabilir. Timeout da başarısız çağrı olarak kullanım
günlüğüne ve circuit breaker'a yazılır.

## Kanıtlı bağlam ve kontrollü yaratıcılık

Proje belleği kaynak dosyalardan yerel olarak sembol ve import/bağımlılık
indeksi çıkarır. Her gerçeklik kartı kaynak dosyanın hash'ine bağlıdır; dosya
değişirse eski kart `stale` olur ve modele doğrulanmış gerçek olarak verilmez.

`AttentionBroker`, hedef görev ve gerçek bağımlılık grafiğine göre en değerli
kanıtları 800 karakterlik ayrı bir bütçe içinde seçer. Dosya varlığı ve hash
bilgisi zaten bağlam başlığında bulunduğu için kanıt kapsülünde tekrarlanmaz.

Model gerekli bir dosya veya sembolü görmüyorsa tahmin etmek yerine:

```json
{
  "action": "need_context",
  "reason": "calculate sembolünün sözleşmesi gerekli",
  "paths": [],
  "symbols": ["calculate"]
}
```

isteği döndürebilir. Prometheus sembol indeksinden yalnızca ilgili dosyayı getirir.
Bir oturumdaki genişletme sayısı ve dosya sayısı ayrıca sınırlandırılmıştır.

Tek-dosya üretiminden sonra `source_evidence_gate` yerel ve göreli named
importları sembol indeksiyle karşılaştırır. Kaynak modülde bulunmayan bir export
uydurulursa dosya yazılmaz ve kullanıcı onayı oluşturulmaz; model yalnızca
kanıtlanan sembollerle yeniden üretim yapmak zorundadır.

Aynı görev planında daha sonra üretileceği açıkça ilan edilen bir modüle import
ise `pending_import` olarak izlenir. Bu geçici durum yalnızca planın kesin dosya
sözleşmesi içindeki yollar için geçerlidir. Modül oluştuktan sonra sembol yine
normal kanıt kapısından geçer; plan dışı dosya veya mevcut modüldeki uydurma
export engellenmeye devam eder.

Yaratıcı fikirler `hypotheses` kasasında gerçeklik kartlarından ayrı saklanır.
Bir hipotez yalnızca doğrulanmış test, araç sonucu veya kullanıcı kararı kanıtı
ile terfi edebilir; yalnızca bir dosyanın var olması terfi için yeterli değildir.

Yerel hesap makinesi ölçümünde eski tam-dosya bağlamı 60.342 karakter, kanıt
kapsülü ve bağımlılık grafiği dahil yeni bağlam 31.685 karakterdir. Bu odaklı
dosya bağlamında `%47,5` azalmadır; oturum geçmişi sıkıştırmasının ek tasarrufu
bu sayıya dahil değildir.

Gerçek sağlayıcı benchmarkında GPT-4.1 mini önce `need_context` ile yalnızca
`applyEncodedOperation` sembolünü istedi, ardından kanıtlanan `plus_v7`
sözleşmesiyle dosyayı üretti. İki model çağrısı 1.876 giriş ve 111 çıkış tokenı
kullandı. Oluşan modül Node ile çalıştırıldı ve `useContract(2, 3) === 5`
doğrulaması geçti.

Boş workspace üzerinde uçtan uca `"Basit bir web hesap makinesi yap."`
benchmarkı 8 GPT-4.1 mini çağrısı, 15.115 giriş ve 3.055 çıkış olmak üzere
toplam 18.170 tokenla tamamlandı. Önceki aynı görev 95.772 token kullanmıştı;
uçtan uca azalma `%81,03` oldu. Üretilen uygulama 8/8 test, production build ve
HTTP 200 kontrollerini geçti.

Focused bağlam seçici değiştiği için önceki bağlam/protokol blokları yeni
`focused-file-v3-context-memory` revizyonunda bir kez güvenli şekilde yeniden
denenebilir.

## Prometheus Arena

Prometheus Arena, gelişmeleri aynı sabit görevlerle tekrar ölçen yerel benchmark
sistemidir. Her koşu yeni ve sınırlandırılmış bir workspace kullanır. Görevin
tamamlanması tek başına başarı sayılmaz: Arena testleri Supervisor'dan bağımsız
olarak yeniden çalıştırır, korunmuş dosyaların değişmediğini doğrular, çağrı ve
token kullanımını ölçer ve sonucu `data/arena.db` içinde saklar.

Mevcut senaryoları görmek ve ücretsiz kota koruma planını model çağrısı yapmadan
incelemek için:

```powershell
python scripts/run_prometheus_arena.py --list
python scripts/run_prometheus_arena.py --scenario js_bugfix
```

Gerçek ücretsiz model çağrısı ancak açık `--live` seçeneğiyle yapılır:

```powershell
python scripts/run_prometheus_arena.py --scenario js_bugfix --live
python scripts/run_prometheus_arena.py --scenario fastapi_task_api --live
python scripts/run_prometheus_arena.py --scenario multi_agent_delivery --live
```

`fastapi_task_api`, gerçek bir backend + QA teslimatını ölçer. Backend uzmanı
izole bir FastAPI görev servisi üretir, QA uzmanı ayrı bir test dosyası yazar;
Arena daha sonra korunan sözleşme testlerini Supervisor'dan bağımsız çalıştırır.
Sağlık kontrolü, görev oluşturma/listeleme, tamamlama, 404/422 hata durumları,
fresh app factory izolasyonu ve QA testlerinin asgari kapsamı birlikte geçmeden
senaryo başarılı sayılmaz. Varsayılan gerçek-dünya hızlı paketi artık frontend
oluşturma, hedefli onarım ve bu backend teslimatını birlikte çalıştırır.

Arena günlük ücretsiz kotanın yapılandırılmış son `%10` bölümünü korur. Koruma
payından sonra senaryonun güvenli biçimde başlayabileceği kadar çağrı yoksa canlı
koşuyu başlatmaz; hiçbir zaman ücretli rotaya geçmez.

Puan 100 üzerinden hesaplanır: görev tamamlama 40, bağımsız doğrulama 25, dosya
sözleşmesi 10, otonomi 10, çağrı/token verimliliği 10 ve güvenilirlik 5 puandır.
Her koşunun ayrıntılı sonucu ayrıca kendi `.adam/arena-result.json` dosyasına
yazılır.

`multi_agent_delivery` senaryosu backend, frontend ve QA görevlerini ayrı
dosya sözleşmeleriyle üç katmana böler. Arena yalnızca son test sonucunu değil,
üç rolün de görevi tamamlamasını ve Supervisor üzerinden gerçek atama/tamamlama
devirlerinin oluşmasını zorunlu tutar. Eksik iş paylaşımı, testler geçse bile
başarılı çok-agent teslimatı sayılmaz ve puanı 70 ile sınırlar.

Kayıtlı sonuçlar model çağrısı yapmadan karşılaştırılabilir:

```powershell
python scripts/run_prometheus_arena.py --show-history
python scripts/run_prometheus_arena.py --scenario python_feature --show-history
```

Web sunucusu çalışırken Arena geçmişi `/arena` adresinden görülebilir.
Aynı ekranda iki koşu seçilerek skor, doğrulama, süre, model çağrısı, token,
görev ve handoff farkları karşılaştırılabilir. Her koşu ayrıntısında deterministik
bir otomatik teşhis; eksik artifact, protected-path ihlali, bloklanan görev,
provider retry ve bağımsız doğrulama hatalarını kanıtlarıyla sınıflandırır ve
bir sonraki inceleme adımını önerir. Teşhisten ayrıca deterministik bir kurtarma
manifesti üretilir. Manifest; kaynak kanıtı koruma, ücretsiz kota preflight,
yeni workspace/history/log yolları, tek canlı koşu sınırı ve açık kullanıcı onay
cümlesini tanımlar. Protected-path ihlali veya bilinmeyen senaryo kimliği varsa
yeniden koşu planını bloklar; sağlıklı teslimatlarda yeni canlı koşu önermez.

Karşılaştırma, teşhis ve recovery planı uçları salt-okunurdur. Yalnızca
`ready_for_approval` durumundaki kayıtlı bir senaryo, kullanıcı manifestteki
onay cümlesini harfiyen yazdıktan sonra `POST` recovery yürütme ucuyla
başlatılabilir. Mutating istek `X-Prometheus-CSRF: 1` başlığını gerektirir.
Sunucu canlı çağrıdan önce ücretsiz kota preflight çalıştırır, aynı anda yalnızca
bir recovery koşusuna izin verir ve aynı kaynak koşudan ikinci bir yürütme
başlatmaz. Yeni koşu, kaynak kanıta dokunmadan ayrı bir workspace kökü, doğrudan
`arena-recovery-*.db` history dosyası ve JSONL log dosyası kullanır. Yürütme
durumu ayrı bir `GET` ucundan izlenir; wrapper seviyesinde otomatik retry yoktur.

Ekran `ARENA_HISTORY_DIRECTORY` altındaki doğrudan `arena*.db` dosyalarını
birleştirir. Koşu listesi, skor, süre, token kullanımı, görevler, handoff'lar,
doğrulama sonuçları ve açık onayla başlatılan recovery yürütmesinin durumu
görüntülenebilir.

Arena ve diğer iç içe workspace'lerde `pytest`, üst dizindeki başka bir projenin
yapılandırmasını yanlışlıkla miras almaması için `--rootdir=.` ve
`--confcutdir=.` ile workspace sınırında tutulur. Workspace kökünde gerçek bir
pytest yapılandırması varsa o kullanılır; yoksa işletim sisteminin nötr
yapılandırma dosyası (`os.devnull`) seçilir. Terminal runtime revizyonu
değiştiğinde eski ortam blokları yalnızca bir kez güvenli biçimde yeniden
değerlendirilebilir.

## Tekrarlanabilir kurulum

Doğrulanan doğrudan bağımlılıklar `requirements.txt` ve
`requirements-dev.txt` içinde sabitlenmiştir. Tüm geçişli bağımlılık grafiği
`requirements-lock.txt` tarafından sınırlandırılır:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Sürekli misyon

Komuta Merkezi artık yeni bir hedefi `auto_start` ile başlatır. Prometheus; görevler
tamamlanana veya kullanıcı kararı, güvenli işlem onayı ya da gerçek bir hata
kapısı oluşana kadar hazır görevleri kendi kendine ilerletir. Paylaşılan
workspace güvenliği için görev yürütme bu sürümde bilinçli olarak seridir.
