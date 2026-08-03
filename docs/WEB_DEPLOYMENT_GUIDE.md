# Web Deployment & Browser Testing Guide

## Kritik Kural: Kullanıcı Testi Önce!

**Her web projesi tamamlandığında**:
1. ✅ Dosyayı tarayıcıda aç
2. ✅ Her özelliği manuel test et
3. ✅ Console'da hata var mı kontrol et
4. ❌ Node testleri geçti = çalışıyor değil!

---

## ES Modules + file:// Protokolü = CORS Hatası

### ❌ Yanlış (Çalışmaz):
```html
<!-- index.html -->
<script type="module" src="app.js"></script>
```
```javascript
// app.js
import { func } from './utils.js';  // CORS hatası!
```

**Sorun**: `file://` protokolü ES modules'i desteklemez.

### ✅ Doğru Çözümler:

#### Çözüm 1: Tek Dosya (Basit Projeler İçin)
```html
<!DOCTYPE html>
<html>
<head>
  <style>/* CSS buraya */</style>
</head>
<body>
  <!-- HTML buraya -->
  <script>
    // JavaScript buraya (module yok)
  </script>
</body>
</html>
```

**Ne zaman kullan**: 
- Basit hesap makinesi, to-do list gibi küçük projeler
- Tek sayfalık uygulamalar
- Prototip/demo

#### Çözüm 2: HTTP Server (Karmaşık Projeler İçin)
```bash
# Python
python -m http.server 8000

# Node
npx http-server

# Ardından: http://localhost:8000
```

**Ne zaman kullan**:
- Çok dosyalı projeler
- ES modules zorunlu
- API çağrıları var

#### Çözüm 3: Build Tool
```bash
# Vite, Webpack vb.
npm run dev
```

---

## Basitlik Kuralı

| Proje Türü | Çözüm |
|------------|-------|
| Hesap makinesi | ✅ Tek HTML |
| To-do list | ✅ Tek HTML |
| Form validation | ✅ Tek HTML |
| SPA (React/Vue) | ❌ Build tool gerekli |
| API entegrasyonu | ⚠️ HTTP server önerilir |

---

## Tarayıcı Test Checklist

Frontend görevi tamamlandığında:

- [ ] `start index.html` komutuyla tarayıcıda açıldı mı?
- [ ] F12 Console'da hata var mı?
- [ ] Network tab'da CORS hatası var mı?
- [ ] Tüm butonlar çalışıyor mu?
- [ ] Hesaplama/işlev sonuç veriyor mu?
- [ ] Hata mesajları görünüyor mu?

**Eğer herhangi biri HAYIR ise → düzelt ve tekrar test et!**

---

## Örnek: Hesap Makinesi

### ❌ Yanlış Yaklaşım (Prometheus'un İlk Hatası)
```
/workspace
  ├── index.html           (module import)
  ├── src/
  │   ├── app.js          (ES module)
  │   └── calculator.js   (ES module)
  └── tests/
      └── test.js         (Node test ✅ ama tarayıcıda ❌)
```

**Sonuç**: Node testleri geçti ama kullanıcı açamadı!

### ✅ Doğru Yaklaşım
```
/workspace
  └── calculator.html     (tek dosya, inline CSS+JS)
```

**Sonuç**: Çift tıkla, açılır, çalışır! 🎯

---

## Genel Kural

**"Çalışıyor" = Kullanıcı dosyayı açıp kullanabiliyor**

Node testleri ≠ Gerçek kullanım

Frontend agent'ın son adımı **mutlaka** tarayıcı testi olmalı.
