"""
Test için farklı placeholder pattern'leriyle PDF oluştur
"""
import fitz
import os

def create_test_pdf():
    """Çeşitli placeholder pattern'leriyle test PDF'i oluştur"""
    print("🔥 Creating test PDF with multiple placeholder patterns...")
    
    # A4 boyutunda yeni PDF oluştur
    doc = fitz.Document()
    page = doc.new_page()
    
    # Farklı placeholder türleri ve konumları
    patterns = [
        ("{{Ad}}", 100, 100),           # Standart
        ("{ {Soyad} }", 100, 150),      # Boşluklu kırlangıç
        ("{Yaş}", 100, 200),            # Tek kırlangıç
        ("[[Şehir]]", 100, 250),        # Köşeli parantez
        ("[ [Ülke] ]", 100, 300),       # Boşluklu köşeli
        ("[Telefon]", 100, 350),        # Tek köşeli
        ("((E-mail))", 100, 400),       # Çift yuvarlak
        ("( (Website) )", 100, 450),    # Boşluklu yuvarlak
        ("{{{ID}}}", 100, 500),         # Üçlü kırlangıç
        ("{[Adres]}", 100, 550),        # Karma 1
        ("[{Meslek}]", 100, 600),       # Karma 2
        ("${Maaş}", 100, 650),          # Dolar
        ("%{Yüzde}%", 100, 700),        # Yüzde
        ("@{Twitter}", 300, 100),       # At işareti
        ("#{Hashtag}", 300, 150),       # Hashtag
    ]
    
    # Her pattern'i PDF'e ekle
    for text, x, y in patterns:
        page.insert_text((x, y), text, fontsize=14, color=(0, 0, 0))
        print(f"✅ Added: {text} at ({x}, {y})")
    
    # Başlık ekle
    page.insert_text((50, 50), "Multi-Pattern Placeholder Test PDF", fontsize=18, color=(0, 0, 1))
    
    # PDF'i kaydet
    output_path = os.path.join(".", "test_multi_pattern.pdf")
    doc.save(output_path)
    doc.close()
    
    print(f"🎯 Test PDF created: {output_path}")
    print(f"📋 Total patterns: {len(patterns)}")
    return output_path

if __name__ == "__main__":
    create_test_pdf()
