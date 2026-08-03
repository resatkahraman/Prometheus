# 31 Temmuz 2026 güncel denetim

Bu belge, masaüstü kopyası üzerinde yapılan salt-okunur denetimin sonucudur.

## Test ve çalışma durumu

- Tam test paketi: 284 geçti.
- Python modülleri derlenebiliyor: compileall app başarılı.
- FastAPI uygulaması import edilebiliyor.
- Prometheus sunucusu denetim sırasında çalışmıyordu; 8765 portunda dinleyici yoktu.
- Yerel Ollama modeli kurulu ve kısa testte doğru yanıt verdi.

Testlerin geçmesi, aşağıdaki gerçek çalışma zamanı ve güvenlik eksiklerinin
çözüldüğü anlamına gelmez.

## Öncelikli bulgular

### 1. Kritik — yanlış workspace kökü

.env içindeki PROMETHEUS_WORKSPACE_ROOT, masaüstü projesi yerine eski
İndirilenler kopyasının workspace klasörünü gösteriyor. Masaüstü kopyası
başlatılırsa görevin ürettiği dosyalar yanlış kopyaya yazılır.

Kabul ölçütü: ayar masaüstü workspace yolunu gösterir; /v1/health ve
/v1/workspace aynı kökü bildirir.

### 2. Kritik — şifresiz masaüstü paylaşımı ve fiziksel tıklama

app/screen_stream.py, masaüstünü MJPEG akışı olarak sunan /screen/feed ve
fiziksel fare tıklaması yapan /screen/click uçlarını ekliyor. app/main.py bu
router'ı koşulsuz yüklüyor. Arayüzler ayrıca autonomy_mode=trusted ile görev
başlatıyor.

Bu özellikler yerel olarak bile varsayılan kapalı olmalıdır. Dış ağ, tünel veya
port yönlendirmesi altında hiçbir şekilde kimlik doğrulamasız çalışmamalıdır.

Kabul ölçütü: varsayılan kurulumda bu rotalar yoktur; yeniden eklenecekse ayrı
feature flag, localhost sınırı, oturum doğrulaması, CSRF koruması ve her
tıklama/otonomi için açık kullanıcı onayı gerekir.

### 3. Yüksek — çalışma alanı bağlamı hâlâ kirli

Workspace içinde Arena, benchmark ve önceki test çıktı klasörleri bulunuyor.
workspace_list denetiminde listelenen 195 dosyanın 172'si bu tür yapay
çıktılardandı. Mevcut filtre; arena, real-world ve pytest-prometheus-* gibi
yolları yeterince dışlamıyor.

Kabul ölçütü: workspace listeleme, arama, planlama ve RAG aynı tekil dışlama
politikasını kullanır; silinmiş dosya kartları project memory'den prune edilir;
yeni kullanıcı görevi eski benchmark kaynaklarını görmez.

### 4. Yüksek — 7B yerel model timeout uyumsuzluğu

qwen2.5-coder:7b-instruct-q3_K_M kısa testte yaklaşık 18 token/s üretti.
Mevcut LOCAL_MODEL_TIMEOUT_SECONDS=45, 900–1000 tokenlik normal adım için
yetersizdir; yalnız üretim süresi bile yaklaşık 50 saniyeyi aşar. Ayar dosyasında
AGENT_STEP_OUTPUT_TOKENS iki kez tanımlanmıştır (900 ve 1000).

Kabul ölçütü: tek kaynaklı çıktı bütçesi; model benchmark sonucuna göre makul
timeout; uzun focused-file üretimlerinde yerel rota için daha küçük çıktı veya
ücretsiz fallback.

### 5. Orta — import sırası bağımlılığı

from app.workspace.policy import WorkspacePolicy doğrudan kullanıldığında
app.tools paketinin eager import davranışı nedeniyle circular import oluşuyor.
Testler belirli import sırasıyla bunu gizliyor.

Kabul ölçütü: WorkspacePolicy doğrudan import testinde hata vermez; app.tools
gereksiz eager registry import etmez veya bağımlılık yönü düzelir.

### 6. Orta — bağımlılık bildirimi eksik

Ekran akışı modülü Pillow kullanıyor. Denetim makinesinin sanal ortamında yüklü
olsa da requirements dosyalarında sabitlenmiş değil. Temiz kurulumda uygulama
başlangıcı bozulabilir.

### 7. Düşük — API kök sözleşmesi değişmiş

/ rotası önceden makine-okunur ürün bilgisi döndürürken şu an HTML laboratuvar
arayüzü döndürüyor. Bu değişiklik isteniyorsa dokümante edilmeli; değilse eski
API sözleşmesi geri gelmeli veya ayrı /v1 kökü eklenmeli.

## Bu denetimde değiştirilmemiş öğeler

- Kaynak kodu ve .env değiştirilmedi.
- Sunucu başlatılmadı.
- Ekran akışı veya fare tıklama uçları çağrılmadı.
- API anahtarları okunmadı, raporlanmadı veya aktarılmadı.

