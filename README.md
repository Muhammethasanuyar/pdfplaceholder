# PDF Placeholder Filler
# PDF Placeholder Filler

Türkçe PDF belgelerindeki `{{placeholder}}` alanlarını otomatik olarak tespit edip dolduran web uygulaması. PyMuPDF (fitz) kullanarak hem metin katmanlı hem de taranmış (OCR) PDF'leri destekler.

## Özellikler

- **Akıllı Placeholder Tespiti**: Metin katmanı, OCR, form alanları ve serbest metin annotasyonlarından placeholder'ları bulur
- **Türkçe Destek**: Unicode fontları ve Türkçe karakter normalizasyonu
- **Çoklu Font Seçimi**: Yerleşik fontlar, sistem fontları ve PDF içindeki gömülü fontları kullanabilme
- **Web Arayüzü**: Kolay kullanım için modern HTML5 arayüzü
- **RESTful API**: Programmatik kullanım için FastAPI tabanlı API
- **Docker Desteği**: Kolay deployment için containerized yapı

## Kurulum

### Ön Gereksinimler

1. **Python 3.8+**
2. **Tesseract OCR** (OCR özelliği için):
   - Windows: [Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki) indirip kurun
   - Ubuntu/Debian: `sudo apt-get install tesseract-ocr tesseract-ocr-tur`
   - macOS: `brew install tesseract tesseract-lang`

### Yerel Kurulum

1. Repository'yi klonlayın:
```bash
git clone <repository-url>
cd pdf-filler
```

2. Virtual environment oluşturun:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# veya
venv\Scripts\activate     # Windows
```

3. Dependencies'leri yükleyin:
```bash
pip install -r requirements.txt
```

4. Uygulamayı çalıştırın:
```bash
python main.py
```

5. Tarayıcıda açın: `http://localhost:8000`

### Docker ile Kurulum

```bash
docker-compose up -d
```

Bu komut otomatik olarak Tesseract OCR ile birlikte uygulamayı başlatır.

## Kullanım

### Web Arayüzü

1. Ana sayfaya gidin (`http://localhost:8000`)
2. PDF dosyasını seçin
3. "Placeholderları Tara" butonuna tıklayın
4. Tespit edilen anahtarlar için değerleri girin
5. "PDF'yi Doldur ve İndir" butonuna tıklayın

### CLI Kullanımı

Basit doldurma işlemi için:
```bash
python fill_placeholders.py input.pdf output.pdf mapping.json --font fonts/DejaVuSans.ttf
```

## API Endpoint'leri

### `/ocr_status`
Tesseract OCR durumunu kontrol eder.

**Response:**
```json
{
  "tesseract_cmd": "/usr/bin/tesseract",
  "available": true
}
```

### `/analyze`
PDF'deki placeholder'ları analiz eder (eski endpoint).

**POST** `multipart/form-data`
- `template`: PDF dosyası

**Response:**
```json
{
  "pages": 5,
  "placeholders": [
    {
      "key": "ad_soyad",
      "key_norm": "ad_soyad",
      "page": 0,
      "rect": [100.0, 200.0, 300.0, 220.0],
      "font_name": "DejaVuSans",
      "font_size": 12.0
    }
  ],
  "unique_keys": ["ad_soyad", "tarih"]
}
```

### `/ai_detect`

  ## Deploy to Render (Docker)

  1. Commit and push this repo to GitHub.
  2. In Render, create a new Web Service:
    - Service type: Docker
    - Repository: this repo
    - Branch: main
    - Root directory: /
    - Auto-Deploy: Yes
    - Instance: Starter or above (512MB+ RAM recommended)
  3. Environment
    - Add environment variable PORT=10000 (Render sets this automatically; Dockerfile respects it)
    - Optional: AI_API_KEY, OCR_LANGS (tur+eng)
  4. Expose HTTP port
    - Render will route to $PORT automatically
  5. Health check path
    - /
  6. Start Command
    - Not needed (Dockerfile CMD runs uvicorn and binds $PORT)

  After deploy, you’ll get a live URL like: https://your-service.onrender.com
Gelişmiş placeholder tespiti (OCR + metin katmanı + formlar).

**POST** `multipart/form-data`
- `template`: PDF dosyası
- `provider`: "auto", "local", "ocr"

**Response:**
```json
{
  "provider_used": "local",
  "pages": 5,
  "placeholders": [...],
  "unique_keys": ["ad_soyad"],
  "warning": null
}
```

### `/fonts`
PDF içindeki gömülü fontları listeler.

**POST** `multipart/form-data`
- `template`: PDF dosyası

**Response:**
```json
{
  "fonts": [
    {
      "xref": 5,
      "name": "DejaVuSans",
      "base": "DejaVu Sans",
      "ext": ".ttf",
      "embedded": true,
      "bytes": 125000,
      "realname": "DejaVuSans.ttf",
      "subset_like": false
    }
  ]
}
```

### `/fill`
PDF'yi doldurur ve sonucu döndürür.

**POST** `multipart/form-data`
- `template`: PDF dosyası
- `fields_json`: Anahtar-değer eşleşmeleri JSON string
- `align_json`: Hizalama ayarları JSON string
- `font_path`: Font dosyası yolu
- `provider`: Tespit sağlayıcısı
- `min_fs`, `max_fs`: Font boyutu aralığı
- `size_mode`: "auto" veya "fixed"
- `text_color`: RGB renk array [r,g,b]
- `selected_font_xref`: PDF içinden font seçimi
- `erase_mode`: "redact" veya "none"

**Response:** Doldurulmuş PDF dosyası

**Headers:**
- `X-Font-Fallback`: Kullanılan font
- `X-Embed-API`: Font embed desteği
- `X-Detect-Fallback`: Tespit fallback bilgisi
- `X-Missing-Keys`: Doldurulmayan anahtarlar

## Development

### Kod Kalitesi

```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8 .

# Run tests
pytest
```

### Environment Variables

- `DEBUG_AI=1`: Detaylı font eşleme logları
- `TESSERACT_CMD`: Tesseract executable yolu
- `OCR_LANGS=tur+eng`: OCR dilleri

## Troubleshooting

### Tesseract OCR Çalışmıyor
- Tesseract'ın kurulu olduğundan emin olun: `tesseract --version`
- `TESSERACT_CMD` environment variable'ını ayarlayın
- Docker kullanıyorsanız image'ın Tesseract içerdiğinden emin olun

### Font Sorunları
- `fonts/` dizinindeki font dosyalarını kontrol edin
- DejaVu Sans genellikle Türkçe karakterler için güvenilirdir
- PDF içindeki gömülü fontları kullanmayı deneyin

### Memory Issues
- Büyük PDF'ler için daha fazla RAM gerekli
- Docker memory limitlerini artırın: `docker run --memory=2g`

## Lisans

Bu proje açık kaynak kodludur. Detaylar için LICENSE dosyasına bakın.

## Katkıda Bulunma

1. Fork edin
2. Feature branch oluşturun: `git checkout -b feature/yeni-ozellik`
3. Commit edin: `git commit -am 'Yeni özellik eklendi'`
4. Push edin: `git push origin feature/yeni-ozellik`
5. Pull Request oluşturun

## Destek

Herhangi bir sorun yaşarsanız GitHub Issues kullanın.


