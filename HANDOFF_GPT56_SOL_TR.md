# Prometheus — GPT-5.6 Sol Devir Belgesi

## Yeni agente verilecek kısa talimat

Bu depoyu baştan yazma. Önce bu belgeyi ve `README.md` dosyasını tamamen oku, ardından mevcut kodu ve testleri incele. Prometheus'u sıradan bir sohbet botu olarak değil, kullanıcının verdiği hedefi gerçek çalışma alanında tamamlayıp çalışan ürünü teslim eden ücretsiz-öncelikli kişisel dijital mühendis olarak geliştir. Antigravity uygulama/terminal katmanı olacak; teknik kararları, kod değişikliklerini ve doğrulama ölçütlerini GPT-5.6 Sol belirleyecek. Her büyük değişiklikten sonra küçük sağlık kontrolü yap, bütün hedef mimari tamamlanınca kapsamlı gerçek dünya kabul sınavını çalıştır. Mevcut çalışan özellikleri gereksiz yere yeniden yazma ve `.env` içeriğini veya API anahtarlarını istemeden görüntüleme.

## Ürün vizyonu

Prometheus'un hedefi şudur:

```text
kullanıcı hedefi verir
→ Prometheus projeyi ve ortamı anlar
→ yalnızca önemli ürün kararlarını sorar
→ işi planlar ve uzman agentlara dağıtır
→ göreve göre en uygun modeli seçer
→ dosyaları gerçekten oluşturur/değiştirir
→ bağımlılıkları ve sunucuları yönetir
→ testleri ve gerçek kullanıcı akışlarını çalıştırır
→ hataları teşhis edip strateji değiştirir
→ bağımsız reviewer ile kanıtları denetler
→ çalışan ürünü ve anlaşılır sonucu teslim eder
```

Bu bir ChatGPT klonu veya yalnızca kod üreten arayüz değildir. Uzun süreli görevleri sürdürebilen, bilgisayar araçlarını kullanabilen, maliyetini yöneten, güvenilir ve genel amaçlı bir agent sistemidir.

Kullanıcının öncelik sırası:

1. Otonomi
2. Güvenilirlik
3. Geniş yetenek
4. Düşük maliyet / mümkün olduğunca ücretsiz kullanım
5. Hız

Önemli işlemlerde kullanıcıya sorulmalı; sıradan ve geri alınabilir teknik adımlar otonom yapılmalıdır. Git şimdilik otomatik mutasyon akışına dahil edilmemelidir. Ücretli modeller kullanıcı daha sonra anahtar ve bütçe ekleyene kadar kapalı kalmalıdır.

## Bugüne kadar yapılanlar

- FastAPI tabanlı supervisor ve web arayüzü kuruldu.
- Planner, Architect, Frontend, Backend, Database, QA, Reviewer, Integration, Calculation ve Worker rolleri bulunuyor.
- Görevler planlanabiliyor, katmanlara ayrılabiliyor ve agentlara atanabiliyor.
- Dosya okuma/yazma, çalışma alanı arama, güvenli terminal, test, hesaplama ve proje özeti araçları var.
- Yerel Ollama ile `qwen3.5:4b` hızlı model ve `qwen3.5:9b` uzman model rotaları bulunuyor.
- Ücretsiz Gemini ve Groq fallback rotaları bulunuyor. GitHub Models rotası üretimde 410 verdiği için rota kataloğunda devre dışı bırakıldı; yapılandırma bilgisi korunuyor.
- Ücretli model kullanımı kapalı: `PAID_MODELS_ENABLED=false`, aylık ücretli bütçe `0`.
- Günlük rota kotaları, görev çağrı bütçesi, tahmini token kullanımı, circuit breaker ve kalite kontrolü mevcut.
- Proje belleği, bağlam derleyici, dikkat bütçesi, yerel embedding, orientation cache ve TLB-benzeri sıcak bağlam yaklaşımı geliştirildi.
- Kanıt uzlaştırma, bağımsız reviewer, tekrar döngüsü koruması, watchdog/heartbeat ve uygulanan araç çağrısından sonra kurtarma yolları eklendi.
- Static HTML/Three.js çıktıları için bozuk JavaScript ve sahte 3B davranışları yakalayan kalite kontrolleri geliştirildi.
- Canlı görev durumu SSE ile arayüze aktarılıyor; model rotası, ilerleme ve sonuç kartı gösteriliyor.
- Görev yaşam döngüsü eklendi: paneli kapatma, arşivleme, kalıcı görev kaydı silme, aynı isteği zorla yeni kimlikle çalıştırma.
- Yerel model kullanımında bellek boşaltma ve zaman aşımı/fallback davranışları iyileştirildi.
- Kontrollü self-improvement, gölge değerlendirme ve gerçek dünya arena/benchmark altyapısı mevcut.

## Son temizlik durumu

2026-08-02 tarihinde eski hesap makinesi, gezegen ve araba denemeleri; eski görev kayıtları; proje belleği; improvement veritabanı; benchmark çıktıları ve agent yedekleri aktif çalışma alanından çıkarıldı. Temiz başlangıç yapıldı.

Aktif görev sayısı: `0`

`workspace/` içinde yalnızca `.gitignore`, `.gitkeep` ve çalışma sırasında yeniden oluşturulabilen `.adam/` durumu bulunmalıdır. Eski dosyalar proje ZIP'ine dahil değildir.

## Mevcut model ve yönlendirme yaklaşımı

- Basit, kısa ve düşük riskli görevler: yerel `qwen3.5:4b`
- Daha zor yerel kodlama/muhakeme: yerel `qwen3.5:9b`
- Yerel modeller kalite kontrolünden geçemezse: ücretsiz API rotaları
- Uzun bağlam veya uygun genel görev: Gemini
- Hızlı ücretsiz fallback: Groq fast
- Daha güçlü ücretsiz fallback: Groq strong
- Ücretli rotalar: kullanıcı açıkça etkinleştirene kadar kapalı

Yerel modele yapay günlük kota konulmamalı; gerçek sınırlar makine kaynağı, zaman aşımı, bağlam uzunluğu ve başarısız tekrar sayısı olmalıdır. Basit görevlerde pahalı/uzak rotaya gereksiz geçiş engellenmeli, fakat yerel modelin kötü çıktısı sonsuz kez tekrarlanmamalıdır.

## Bilinen önemli sorunlar

1. Uçtan uca otonom teslimat henüz güvenilir değil. Kod üretilebiliyor fakat bazı görevler durum makinesinde takılabiliyor veya çıktı gerçekten çalıştırılmadan süreç sapabiliyor.
2. Yerel küçük model zaman zaman sözdizimsel olarak bozuk veya görünüşte ikna edici fakat çalışmayan kod üretiyor. Kalite kapıları genişletilmeli; model cevabını doğrudan ürün kabulü saymamak gerekir.
3. Çoklu agent rolleri var fakat `supervisor_single_active_task=true`; gerçek güvenli paralel görev yürütme henüz tamamlanmadı.
4. Prometheus'un kendi genel amaçlı internet araştırması ve tarayıcı kontrol araçları hedeflenen seviyede değil.
5. Bağımlılık kurulumu, geliştirme sunucusu yaşam döngüsü, port tespiti, uygulamayı açma ve kapatma uçtan uca sağlamlaştırılmalı.
6. Görsel uygulamalarda yalnızca dosya/test kanıtı yeterli değil; gerçek tarayıcı çalıştırması, konsol hatası, etkileşim ve ekran görüntüsü doğrulaması gerekiyor.
7. Aynı görev veya başarısız continuation çağrılarında geçmişte `resume_ignored_no_state_change` döngüsü yaşandı. Koruma eklendi fakat gerçek stres testi yapılmalı.
8. Kullanıcı arayüzü ilerlemeyi daha iyi gösteriyor ancak “şu an ne yapıyor, neden bekliyor, sonuç nerede” sorularına her durumda açık cevap vermeli.
9. Self-improvement parçaları var ancak güvenli sandbox → test → karşılaştırma → onay → rollback zinciri üretim seviyesinde tamamlanmadı.
10. Son tam regresyon koşumunda 311 test geçti. İki eski beklenti hâlâ sorunlu görünüyordu: ücretsiz görev bütçesi/fallback davranışı ve genel görevlerde uzak rota sıralaması. Önce bunların gerçek ürün hatası mı, eski test beklentisi mi olduğu belirlenmeli.

## Sıradaki geliştirme planı

### Aşama 1 — Çalışma motorunu güvenilir hale getir

1. Supervisor durum makinesini resmîleştir; her durum için izin verilen geçişleri ve terminal durumları tanımla.
2. Tekrarlanan görev, arşivleme, iptal, silme, yeniden başlatma ve uygulama yeniden açılması senaryolarını stres testine sok.
3. Heartbeat/watchdog mekanizmasını gerçek uzun görevler ve model zaman aşımıyla doğrula.
4. Her başarısızlıkta yapılandırılmış hata sınıfı, kök neden ve uygulanabilir sonraki adım üret.
5. Agentın aynı değişmeyen çağrıyı tekrar etmesini engelle; yeni kanıt veya strateji yoksa farklı rota/plan seç.

### Aşama 2 — Gerçek araç ve ürün teslimi

1. Güvenli tarayıcı kontrolü ve internet araştırma araçları ekle.
2. Paket yöneticisi ve bağımlılık kurulumunu risk seviyesine göre onaylı/otonom hale getir.
3. Sunucu süreç yöneticisi ekle: başlat, PID/port izle, logları aktar, sağlık kontrolü yap, güvenli kapat.
4. Web ürünleri için otomatik Playwright benzeri kabul testi ekle.
5. Konsol hataları, ağ hataları, görünür UI, tıklama/klavye akışı ve ekran görüntüsü kanıtını reviewer'a ver.
6. Sonuç tesliminde tıklanabilir dosya/URL, çalıştırma talimatı, test sonucu ve kullanılan kaynakları göster.

### Aşama 3 — Gerçek çoklu agent iş paylaşımı

1. Dosya sahipliği ve bağımlılık grafiğiyle çakışmayan görevleri paralel çalıştır.
2. Aynı dosyaya yazan agentları kilitle veya ayrı worktree/sandbox içinde çalıştır.
3. Integration agentına yalnızca doğrulanmış artefaktları birleştirme sorumluluğu ver.
4. Reviewer'ı üretici agenttan ve mümkünse üretici model rotasından bağımsız tut.
5. Paralellik kazancını süre, token, çakışma ve başarı oranıyla ölç.

### Aşama 4 — Token verimliliği ve kalite

1. Tam dosyaları sürekli modele göndermek yerine sembol/diff/ilgili kesit tabanlı bağlam kullan.
2. Proje belleğine yalnızca kanıtlı ve güncel bilgileri yaz; kaynak dosya hash'i değişince geçersiz kıl.
3. Attention/TLB-benzeri sıcak bağlam önbelleğini gerçek görevlerde benchmark et.
4. Yerel 4B model için dar, araç odaklı görevler; 9B ve API modelleri için karmaşık görevler tanımla.
5. Router'ı yalnız sezgisel puanla değil görev türü × model × başarı × süre × token geçmişiyle kalibre et.
6. Kalite düşmeden token azaltımını A/B arena ile kanıtla.

### Aşama 5 — Güvenli self-improvement

1. Başarısızlık kümelerinden iyileştirme hipotezi üret.
2. Değişikliği ana koddan ayrı sandbox/worktree üzerinde uygula.
3. Tam regresyon, hedef test ve gerçek dünya senaryosunu çalıştır.
4. Eski/yeni sürümü başarı, hız, token, maliyet ve güvenlik açısından karşılaştır.
5. Yalnızca anlamlı ve kanıtlı iyileştirmeyi kullanıcıya öner.
6. Uygulama öncesi geri dönüş noktası oluştur; otomatik ana dal/Git mutasyonu şimdilik yapma.

### Aşama 6 — Komuta Merkezi

1. Kullanıcı diliyle durum göster: “planlıyor”, “yerel model kod yazıyor”, “test çalışıyor”, “API fallback'e geçti”, “kararın gerekiyor”.
2. Her görev için süre, kullanılan model, token/kota, dosyalar, testler ve sonuç bağlantısını göster.
3. Takılmış görev için tek tıkla durdur, arşivle, yeniden dene, farklı modelle dene seçenekleri sun.
4. Ham event adlarını ana kullanıcı çıktısı olarak gösterme; teknik ayrıntıyı açılır tanılama paneline taşı.

## Nihai kabul sınavı

Tüm ana geliştirmelerden sonra temiz bellek ve temiz `workspace/` ile en az şu senaryolar çalıştırılmalı:

1. Tek dosyalı, etkileşimli ve görsel olarak doğrulanan hesap makinesi.
2. Dönen ve kullanıcı etkileşimli 3B gezegen; konsol hatası olmamalı.
3. Çok dosyalı küçük web uygulaması; frontend + backend + veri saklama.
4. Var olan projedeki gerçek bug'ı bulma ve regresyon testiyle düzeltme.
5. Bozuk test paketini teşhis etme ve yalnız doğru kodu/test beklentisini değiştirme.
6. Yerel model başarısızlığından ücretsiz API fallback'ine geçip görevi tamamlama.
7. API kesintisinde güvenli durma ve daha sonra devam etme.
8. Aynı isteği art arda bağımsız görev kimlikleriyle çalıştırma.
9. Uzun görevi kapatma/açma veya sunucu yeniden başlatma sonrasında devam ettirme.
10. Birden fazla agentın paralel çalışıp çakışmadan ürün teslim etmesi.

Her senaryoda ölç:

- Uçtan uca başarı
- Kullanıcı müdahalesi sayısı
- Toplam süre
- Yerel ve uzak model çağrıları
- Giriş/çıkış token tahmini
- Ücretsiz kota kullanımı
- Test ve gerçek kullanıcı akışı sonucu
- Reviewer doğru kabul/ret oranı
- Hata sonrası toparlanma

Hedef önce en az `%80`, ardından `%95` güvenilir görev tamamlama oranıdır.

## Çalışma kuralları

- Önce mevcut kodu ve ilgili testleri oku; çalışan sistemi sıfırdan yeniden yazma.
- `.env`, API anahtarları ve kullanıcı sırlarını çıktıya basma veya repoya ekleme.
- Kullanıcının mevcut değişikliklerini ve alakasız dosyalarını koru.
- Riskli, geri döndürülemez veya dış dünyaya etkisi olan işlemlerde kullanıcıya sor.
- Git'e otomatik commit/push yapma; kullanıcı şimdilik Git mutasyonunu istemiyor.
- Ücretli model kullanımını kullanıcı açıkça etkinleştirmeden açma.
- Her değişikliği kanıtla: hedef test + ilgili regresyon + gerekiyorsa gerçek tarayıcı testi.
- “Dosya yazıldı”yı “ürün çalışıyor” kanıtı sayma.
- Ham model çıktısını doğrudan dosyaya kabul etmeden sözdizimi, kalite, davranış ve güvenlik kontrolünden geçir.
- Büyük mimariyi tamamlayana kadar her modülde kısa sağlık kontrolü yap; ayrıntılı optimizasyonu nihai kabul sınavından gelen ölçümlere göre yap.

## İlk yapılacak iş

1. Depoyu ve bu belgeyi incele.
2. Mevcut test paketini çalıştır.
3. Kalan iki regresyonu kök neden düzeyinde sınıflandır.
4. Yukarıdaki yol haritasını kodun gerçek durumuna göre doğrula ve gerekirse düzelt.
5. Aşama 1'den başlayarak uygula; her anlamlı adımda kısa test yap.
6. Ana geliştirmeler tamamlanınca temiz gerçek dünya kabul sınavını çalıştır ve ayrıntılı rapor üret.

