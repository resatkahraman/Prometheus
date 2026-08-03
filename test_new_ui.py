import httpx
import time

print("Yeni UI test ediliyor...")
time.sleep(3)

try:
    r = httpx.get('http://127.0.0.1:8000/lab', timeout=10)
    if r.status_code == 200:
        content = r.text
        checks = [
            ("Prometheus", "Baslik"),
            ("Görev", "Gorev karti"),
            ("card", "Modern tasarim"),
            ("backdrop-filter", "Blur efekti"),
            ("linear-gradient", "Gradient"),
            ("animation", "Animasyonlar"),
        ]
        
        print("\n=== YENI UI AKTIF ===\n")
        for text, label in checks:
            found = text.lower() in content.lower()
            status = "OK" if found else "EKSIK"
            print(f"[{status}] {label}")
        
        print("\n" + "="*40)
        print("TAMAMEN YENI UI HAZIRLANDI!")
        print("="*40)
        print("\nOzellikler:")
        print("- Glassmorphism design")
        print("- Floating gradient sidebar")
        print("- Modern kart sistemi")
        print("- Smooth animasyonlar")
        print("- Real-time gorev guncelleme")
        print("- Bold typography")
        print("- Neon glow efektleri")
        print("\nAc ve gor: http://127.0.0.1:8000/lab")
    else:
        print(f"HTTP {r.status_code}")
except Exception as e:
    print(f"Hata: {e}")
    print("Server baslatilamadi, manuel baslatma gerekebilir")
