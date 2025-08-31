"""
Aynı isimli multiple placeholder'ları test et
"""
import fitz
import os

def create_multiple_same_key_pdf():
    """Aynı key'e sahip multiple placeholder'larla test PDF'i oluştur"""
    print("🔥 Creating PDF with multiple same-key placeholders...")
    
    # A4 boyutunda yeni PDF oluştur
    doc = fitz.Document()
    page = doc.new_page()
    
    # Aynı key'li placeholders farklı yerlerde
    placeholders = [
        ("{{Ad}}", 100, 100),      # Ad placeholder 1
        ("{{Ad}}", 300, 100),      # Ad placeholder 2 (aynı key)
        ("{{Soyad}}", 100, 200),   # Soyad placeholder 1
        ("{{Soyad}}", 300, 200),   # Soyad placeholder 2 (aynı key)
        ("{{Soyad}}", 100, 300),   # Soyad placeholder 3 (aynı key)
        ("{{Email}}", 100, 400),   # Email placeholder (unique)
    ]
    
    # Her placeholder'ı PDF'e ekle
    for text, x, y in placeholders:
        page.insert_text((x, y), text, fontsize=14, color=(0, 0, 0))
        print(f"✅ Added: {text} at ({x}, {y})")
    
    # Başlık ekle
    page.insert_text((50, 50), "Multiple Same-Key Placeholder Test PDF", fontsize=18, color=(0, 0, 1))
    
    # PDF'i kaydet
    output_path = os.path.join(".", "test_multiple_same_key.pdf")
    doc.save(output_path)
    doc.close()
    
    print(f"🎯 Test PDF created: {output_path}")
    print(f"📋 Expected results:")
    print("  - Ad: 2 instances at (100,100) and (300,100)")
    print("  - Soyad: 3 instances at (100,200), (300,200), (100,300)")
    print("  - Email: 1 instance at (100,400)")
    return output_path

if __name__ == "__main__":
    create_multiple_same_key_pdf()
