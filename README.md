# Eski Usul AI Studio — v0.5.0

Windows 11 üzerinde yerel çalışan, Türkçe arayüzlü tam donanımlı içerik üretim stüdyosu. Veritabanı ve medya dosyaları proje klasöründeki `data/` altında tutulur. Sunucu varsayılan olarak yalnızca `127.0.0.1` üzerinden erişilebilir.

## v0.5.0 ile Eklenen Tam Yetenekler
1. **Paralel & Hibrit Ajan Orkestrasyonu**: 
   - Araştırma Analisti ve İzleyici Stratejisti eşzamanlı çalışır.
   - Doğrulama (Fact Checker), Görsel Prodüksiyon ve Dil Editörü eşzamanlı çalışır. Üretim süresi yarı yarıya kısaltıldı.
2. **Otomatik TTS (Edge-TTS) Doğal Seslendirme**:
   - Harici ücretli API anahtarı gerektirmeden, tek tıkla stüdyo kalitesinde bilge/sıcak Türkçe seslendirme (`tr-TR-AhmetNeural` & `tr-TR-EmelNeural`) oluşturulur.
3. **Pexels & Pixabay Otomatik Stok Video Entegrasyonu**:
   - Visual Producer'ın ürettiği terimlerle dikey HD stok videolar aranabilir ve tek tıkla ticari onaylı olarak arşive indirilebilir.
4. **Sahne Bazlı Akıllı FFmpeg Montajı & Altyazı Gömme**:
   - Her sahnenin saniye zamanlamasına göre medyalar otomatik kırpılır.
   - Altyazılar (.srt) video içine estetik biçimde gömülür (burn-in subtitles).
5. **TikTok Hazır Yayın Paketi**:
   - Video (MP4) + Caption (Açıklama TXT) + Hashtagler + Metadata tek ZIP olarak dışa aktarılır.
6. **SSE Canlı Akış & Kesintisiz Takip**:
   - Polling gerektirmeden tarayıcıda ajanların çalışma durumu anlık olarak akar.

## Gereksinimler
- Windows 11
- Python 3.10, 3.11 veya 3.12
- Gemini API anahtarı veya yerel Ollama
- FFmpeg (video montajı için PATH'e eklenmiş olmalı)
- (Opsiyonel) Ücretsiz Pexels ve Pixabay API anahtarları

## Başlatma
`start_windows.bat` dosyasına çift tıklayın. Tarayıcınızda `http://127.0.0.1:8765` otomatik açılacaktır.
