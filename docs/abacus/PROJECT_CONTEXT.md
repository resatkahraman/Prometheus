# Prometheus proje bağlamı

## Ürün hedefi

Prometheus bir sohbet botu değil; kullanıcının yazılım görevlerini güvenli biçimde
planlayan, alt görevlere ayıran, dosya üreten, araçları kullanan ve sonucu test
kanıtıyla doğrulayan yerel-öncelikli bir geliştirme agentidir.

Öncelik sırası:

1. Güvenilirlik ve somut doğrulama
2. Güvenli otonomi ve önemli işlemlerde kullanıcı onayı
3. Geniş yetenek
4. Düşük maliyet / ücretsiz rotalar
5. Hız

## Başlıca bileşenler

| Alan | Konum | Sorumluluk |
|---|---|---|
| HTTP uygulaması | app/main.py | FastAPI ömrü, API ve UI rotaları |
| Supervisor | app/supervisor/service.py | Plan, görev yaşam döngüsü, onaylar, doğrulama |
| Agent motoru | app/agent/engine.py | Model adımı, araç çağrısı, çıktı kalite kapıları |
| Rota seçimi | app/orchestration/ | Yerel / ücretsiz sağlayıcı puanlama, kota, devre kesici |
| Güvenli araçlar | app/tools/ | Workspace, terminal ve dosya işlemleri |
| Bellek/RAG | app/memory/ | Hash-bağlı sembol ve kanıt hafızası |
| Planlama | app/planning/ | Deterministik görev grafiği üretimi |
| İyileştirme | app/improvement/ | Kanıtla terfi eden Forge adayları |
| Kullanıcı arayüzü | app/lab_ui.py | Ana görev arayüzü (/lab) |

## Normal görev akışı

Kullanıcı hedefi → planlayıcı → görev / kesin dosya / doğrulama sözleşmesi →
ilgili bağlam ve hafıza → yerel model veya ücretsiz fallback → güvenli yazma/onay →
test / build → kanıt incelemesi → tamamlandı veya gerekçeli yeniden planlama.

## Çalışma alanı

Masaüstü kopyasının amaçlanan çalışma alanı:

    C:/Users/Reşat/Desktop/Prometheus/workspace

Ancak mevcut .env dosyasında PROMETHEUS_WORKSPACE_ROOT eski İndirilenler
kopyasına işaret etmektedir. Bu, ilk düzeltilmesi gereken yapılandırma hatasıdır.
Kullanıcı onayı olmadan gerçek kaynakları veya mevcut workspace içeriğini silme.

## Yerel model yaklaşımı

- Birincil yerel sağlayıcı: Ollama
- Mevcut model: qwen2.5-coder:7b-instruct-q3_K_M
- Yerel model düşük riskli, kısa bağlamlı ve test kapılı dosya işleri için ilk
  deneme olabilir.
- Biçim veya kalite başarısızlığında aynı çağrıyı körlemesine tekrarlamak yerine
  ücretsiz uzak fallback kullanılmalıdır.
- Yerel modelin başarısı gerçek dosya ve test kanıtı olmadan kabul edilmez.

