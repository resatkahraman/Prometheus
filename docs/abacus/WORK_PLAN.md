# Önerilen düzeltme sırası

## Aşama 1 — güvenli başlangıç

1. Yanlış PROMETHEUS_WORKSPACE_ROOT ayarını masaüstü kopyasına yönlendir.
2. Ekran akışı / tıklama / uzaktan trusted görev başlatma eklentilerini varsayılan
   kapalı hâle getir veya kaldır.
3. Pillow bağımlılığını feature korunacaksa requirements lock dosyalarına ekle;
   korunmayacaksa modülü kaldır.
4. Doğrudan WorkspacePolicy import testini ekleyip circular import'u düzelt.

## Aşama 2 — takılma sorununu çöz

1. Workspace politika, listeleme, arama, planlama ve RAG için ortak artifact
   dışlama tanımı oluştur.
2. Project memory'de diskten silinen dosyaların kanıt kartlarını stale/prune et.
3. package.json test scriptine göre Node native test, Vitest ve diğer runner
   argümanlarını ayır.
4. Devre kesici geçici açıksa görevi kalıcı bloke etmek yerine bekleme veya
   uygun ücretsiz fallback kullan.
5. Tekrarlanan resume_ignored_no_state_change olaylarını sadeleştir ve UI'da
   anlaşılır aksiyon göster.

## Aşama 3 — yerel model profili

1. Mevcut 7B model için gerçek görev benchmark'ı yap: kısa patch, dosya üretimi,
   test onarımı.
2. Ölç: soğuk/yüklü gecikme, token/s, RAM/VRAM, protokol uyumu, test geçiş oranı.
3. Timeout ve çıktı bütçelerini ölçüme göre ayarla.
4. Hızlı yerel rota ile güçlü yerel rota ayrımını yalnızca veri destekliyorsa ekle.
5. Yerel kalite/protokol hatasında ücretsiz uzak modele kontrollü fallback uygula.

## Aşama 4 — gerçek dünya doğrulaması

1. Boş workspace'te sıfırdan hesap makinesi.
2. Var olan vanilla JavaScript uygulamasında onarım.
3. JavaScript bugfix.
4. Python özellik geliştirme.
5. Çok-agent teslimat.

Her senaryoda planın, dosyaların, test/build kanıtının ve token kullanımının ayrı
raporu tutulmalıdır.

