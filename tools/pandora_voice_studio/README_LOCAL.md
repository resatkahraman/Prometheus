# Pandora Voice Studio — yerel kurulum ve seçim

Pandora’nın sesi iki parçadan oluşur:

1. **VoxCPM2 voice design:** Ücretsiz Colab GPU üzerinde bir defalık özgün aday üretimi.
2. **Chatterbox Multilingual V3:** Seçilen Pandora referansını kullanarak PC’de tamamen yerel Türkçe TTS.

Tarayıcı/Windows sesi, cloud TTS, ücretli API veya gerçek kişi klonu kullanılmaz.

## 1. Onarım paketini uyguladıktan sonra testler

Prometheus proje kökünde:

```powershell
$Py = ".\.venv\Scripts\python.exe"

& $Py -m pytest -q `
  tests/test_pandora_voice_config.py `
  tests/test_pandora_voice_normalization.py `
  tests/test_pandora_voice_import.py `
  tests/test_pandora_voice_studio.py `
  tests/test_pandora_voice_runtime.py `
  tests/test_pandora_tts_worker.py `
  tests/test_pandora_voice_setup_script.py
```

Focused testler geçmeden full pytest çalıştırma. Geçince yalnız bir kez:

```powershell
& $Py -m pytest -q
```

## 2. Pandora adaylarını üret

`tools/pandora_voice_studio/PANDORA_VOICE_DESIGN_COLAB.ipynb` dosyasını Google Colab’a yükle.

Notebook:

- API key istemez.
- Drive bağlamaz.
- On iki özgün kadın sesi adayı üretir.
- Dinlediğin en fazla üç adayı shortlist’e alır.
- Sekiz kalite klibi ve hash doğrulamalı ZIP üretir.

İndirilecek dosya:

```text
pandora_voice_candidates.zip
```

## 3. Voice Studio’yu aç

Studio, ana Prometheus `.venv` ortamındaki FastAPI/uvicorn ile yalnız loopback üzerinde çalışır:

```powershell
Set-Location "<PROMETHEUS_PROJECT_ROOT>"
& ".\.venv\Scripts\python.exe" -m tools.pandora_voice_studio.server
```

Terminalde token içeren yerel URL görüntülenir. Bu URL yalnız aynı PC’de açılır.

Studio’da:

1. ZIP yolunu gir.
2. Adayı aç.
3. Sekiz klibin tamamını dinle.
4. Beğenmediğini reddet veya not ekle.
5. `Pandora olarak seç` düğmesine bas.
6. Exact `SELECT PANDORA <candidate_id>` onayını yaz.

Master dosyalar şuraya yazılır:

```text
%LOCALAPPDATA%\Prometheus\pandora_voice\master
```

WAV dosyaları Git’e eklenmez.

## 4. Yerel TTS runtime’ını kur

Önce dry-run:

```powershell
.\scripts\setup_pandora_tts.ps1
```

Sonra isolated environment ve exact model revision:

```powershell
.\scripts\setup_pandora_tts.ps1 -Apply -DownloadRuntimeModel
```

Doğrulama:

```powershell
.\scripts\setup_pandora_tts.ps1 -VerifyOnly
```

Ana `.venv` değiştirilmez. Runtime:

```text
%LOCALAPPDATA%\Prometheus\venvs\pandora-tts
```

## 5. Worker’ı başlat

```powershell
$TtsPy = Join-Path $env:LOCALAPPDATA "Prometheus\venvs\pandora-tts\Scripts\python.exe"
& $TtsPy ".\tools\pandora_tts_worker.py"
```

Worker yalnız:

```text
127.0.0.1:9723
```

üzerinde dinler. Token plaintext loglanmaz; yerel state dosyasıyla Prometheus Core’a aktarılır.

## 6. RTX 3050 Ti benchmark

Worker açıkken:

```powershell
& ".\.venv\Scripts\python.exe" ".\scripts\benchmark_pandora_tts.py"
```

Sonuç:

```text
%LOCALAPPDATA%\Prometheus\pandora_voice\runtime_benchmark.json
```

Minimum kapılar:

```text
CUDA OOM yok
process peak reserved VRAM <= 3800 MiB
short response <= 4.0 saniye
20 saniyelik ve long-form RTF <= 1.25
```

Kapı geçmezse mobil Pandora geliştirmesine devam edilmez. Browser/Windows sesine sessiz fallback yapılmaz.

## Güvenlik

- Voice Studio ve worker yalnız loopback bind kullanır.
- Candidate ZIP path traversal, symlink, compression bomb ve hash değişikliklerine karşı doğrulanır.
- Studio mutasyonları local random token ister.
- Worker tokenı URL’ye veya loga yazılmaz.
- Onay, token, parola, API key ve exact Windows path içeren metinler ses cache’ine alınmaz.
- Model, candidate WAV, master WAV, cache ve token Git’e eklenmez.
