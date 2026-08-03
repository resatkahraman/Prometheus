# Güvenli çalışma sınırları

## Kesinlikle yasak

- .env, API anahtarları, oturum bilgileri veya kullanıcı verilerini dışarı
  yüklemek, loglamak ya da yanıtta göstermek.
- Git başlatmak, GitHub'a göndermek, commit/push yapmak.
- Workspace kökünü, kaynak dizinini veya geniş klasörleri silmek/taşımak.
- Kimlik doğrulamasız ekran paylaşımı, masaüstü kontrolü veya dış ağ dinleyicisi
  açmak.
- Kullanıcının açık talebi olmadan trusted otonomiyle yeni görev başlatmak.

## Dışlanacak yollar

    .env
    .venv/
    .tools/
    data/
    workspace/.adam/
    workspace/node_modules/
    workspace/dist/
    workspace/build/
    workspace/arena*/
    workspace/*benchmark*/
    workspace/real-world/
    workspace/pytest-prometheus-*/
    .test-tmp*/
    .pytest_cache/
    __pycache__/

Bu yollar yalnızca gerektiğinde, kullanıcı onayıyla ve dar kapsamda incelenebilir.
Hiçbiri yeni görevin ürün kaynak bağlamına otomatik olarak dahil edilmemelidir.

## Değişiklik disiplini

1. Önce sorunu yeniden üret ve kanıtı kaydet.
2. En küçük güvenli değişikliği öner.
3. Değiştirilecek dosyaları ve testleri açıkla.
4. Uygulandıktan sonra hedef testi, ardından tam test paketini çalıştır.
5. Kullanıcıya dosya yolları, test sonucu ve kalan risklerle rapor ver.

## Yerel sunucu

Güvenlik bulguları çözülene kadar dış ağda dinleme, port yönlendirme veya tünel
kullanma. Yerel geliştirme gerekiyorsa yalnızca 127.0.0.1 üzerinde çalıştır.

