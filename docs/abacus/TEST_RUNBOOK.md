# Test ve doğrulama rehberi

## Hızlı kod testi

PowerShell'i proje kökünde aç:

    .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .test-tmp-abacus

Geçici dizin .test-tmp-abacus yalnızca test içindir; ürün workspace'i içinde
oluşturulmamalıdır.

## Önerilen hedef testler

    .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests\test_terminal_runtime_v4.py tests\test_workspace_policy.py

## Derleme denetimi

    .\.venv\Scripts\python.exe -m compileall -q app

## Yerel model benchmark prensibi

- Modeli doğrudan küçük, zararsız ve tekrarlanabilir promptlarla ölç.
- API anahtarlarını, kullanıcı dosyalarını veya .env içeriğini prompta koyma.
- Soğuk yükleme ve yüklü model sonuçlarını ayrı ölç.
- Çıktı bütçesi, seçilen timeout değerinden güvenli biçimde tamamlanabilmeli.

## Sunucu smoke testi

Bu adım yalnızca CURRENT_AUDIT.md içindeki ekran paylaşımı güvenlik sorunu
giderildikten sonra çalıştırılmalıdır:

    .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765

Sonra ayrı bir terminalde:

    Invoke-RestMethod http://127.0.0.1:8765/v1/health

Yanıttaki workspace kökü masaüstü Prometheus workspace'iyle eşleşmelidir.

