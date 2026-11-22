# Eski Usul AI Studio — İş Akışı ve Görev Listesi (v0.4 Hedefi)

> **Amaç:** `reels-af` ve `remotion-superpowers` açık kaynak projelerinden güvenli, hafif ve yüksek değerli özellikleri (Audio Ducking, Safe-Zone Altyazı, ffprobe Senkronizasyonu) Eski Usul felsefesine ve UI/UX tasarımına entegre etmek.

---

## 1. Mimari Kararlar ve Repolardan Alınan Özellikler

| Özellik | Kaynak Repo | Uygulama Yöntemi | Güvenlik & Risk Değerlendirmesi |
| :--- | :--- | :--- | :--- |
| **TikTok Safe-Zone Altyazı** | `Agent-Field/reels-af` | FFmpeg `subtitles` filtresinde MarginV (alt boşluk 220px), Arial/Montserrat kalın font, sarı/beyaz yüksek kontrast. | **Sıfır Risk.** Harici paket gerektirmez, doğrudan FFmpeg ile çalışır. |
| **ffprobe Ses-Sahne Senkronu** | `Agent-Field/reels-af` | Ses dosyasının milisaniyelik süresini okuyarak sahne sürelerini orantılı eşitleme. | **Sıfır Risk.** Videonun sesten erken bitmesini engeller. |
| **Audio Ducking (Akıllı Müzik Kısma)** | `DojoCodingLabs/remotion-superpowers` | Remotion eklemeden, saf FFmpeg `sidechaincompress` ve `amix` filtreleriyle seslendirme varken fon müziğini otomatik kısma. | **Sıfır Risk.** Node.js/Remotion yükü getirmez, Python/FFmpeg ile yerel kalır. |
| **UI/UX Stüdyo Revizyonu** | Eski Usul Marka Dili | Dikey mobil önizleme çerçevesi, altyazı stil seçici, ambians müzik kütüphanesi ve modernleştirilmiş buton hiyerarşisi. | **Yüksek UX Değeri.** Kullanıcı deneyimini profesyonel hale getirir. |

---

## 2. Görev Listesi (Task Board)

### 🟢 Aşama 1: Ses & Video Motoru İyileştirmeleri (`app/video_editor.py`)
- [x] **Görev 1.1:** `ffprobe` ile seslendirme dosyasının tam süresini ölçen yardımcı fonksiyon ekle.
- [x] **Görev 1.2:** Sahnelerin toplam süresini ses dosyasının süresine göre milisaniyelik olarak otomatik kalibre et.
- [x] **Görev 1.3:** FFmpeg Safe-Zone (1080x1920 dikeyde alttan 220px boşluk, TikTok kullanıcı adı ve butonlarıyla çakışmayan) altyazı stilini tanımla.
- [x] **Görev 1.4:** Telifsiz arka plan fon müziği ve Audio Ducking mikserini ekle.

### 🟡 Aşama 2: Backend & API Rotaları (`app/main.py`)
- [x] **Görev 2.1:** Fon müziği seçenekleri ve altyazı stil tercihlerini `/api/export/{script_id}` endpoint'ine parametre olarak ekle.
- [x] **Görev 2.2:** Hata yanıtlarını daha zengin ve açıklayıcı JSON formatına getir.

### 🔵 Aşama 3: UI & UX Designer Dokunuşları (`app/static/`)
- [x] **Görev 3.1:** 9:16 Dikey Video Önizleme ve Mobil Stüdyo Çerçevesi.
- [x] **Görev 3.2:** Altyazı stili ve fon müziği kontrol seçenekleri.
- [x] **Görev 3.3:** Canlı işlem durumu adımlarının mikro-animasyonları ve şık toast bildirimleri.
