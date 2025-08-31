#!/usr/bin/env python3
"""
📋 Örnek PDF Analiz ve Problem Teşhisi
Bu script, kullanıcının attığı Örnek.pdf'yi analiz eder ve problemleri tespit eder:
1. "NEW" yazısının yanlış silinmesi 
2. "sitead" placeholder'ından birinin doldurulmaması
"""

import requests
import json
from pathlib import Path

BASE_URL = "http://localhost:8011"
PDF_PATH = "C:\\Users\\Muhammet\\Desktop\\Ornek.pdf"

def analyze_ornek_pdf():
    """Örnek.pdf'yi detaylı analiz eder"""
    
    print("📋 ÖRNEK PDF DETAYLI ANALİZ")
    print("=" * 50)
    
    # 1. PDF varlığını kontrol et
    pdf_file = Path(PDF_PATH)
    if not pdf_file.exists():
        print(f"❌ PDF dosyası bulunamadı: {PDF_PATH}")
        return
    
    print(f"📁 PDF dosyası: {pdf_file.name}")
    print(f"📊 Dosya boyutu: {pdf_file.stat().st_size:,} bytes")
    
    # 2. PDF'yi analiz et
    print(f"\n🔍 PLACEHOLDER TESPİT ANALİZİ:")
    print("-" * 30)
    
    with open(PDF_PATH, 'rb') as f:
        files = {'file': f}
        response = requests.post(f"{BASE_URL}/api/analyze", files=files)
    
    if response.status_code != 200:
        print(f"❌ Analiz hatası: {response.status_code}")
        print(f"Response: {response.text}")
        return
    
    data = response.json()
    if not data.get("success"):
        print(f"❌ Analiz başarısız: {data.get('message')}")
        return
    
    session_id = data["session_id"]
    placeholders = data["placeholders"]
    
    print(f"✅ Analiz başarılı!")
    print(f"📊 Session ID: {session_id}")
    print(f"🎯 Tespit edilen placeholder sayısı: {len(placeholders)}")
    
    # 3. Placeholder detayları
    print(f"\n📍 PLACEHOLDER DETAYLARI:")
    print("-" * 30)
    
    sitead_count = 0
    for i, ph in enumerate(placeholders, 1):
        key = ph.get("key", "")
        pattern = ph.get("pattern", "")
        page = ph.get("page", 0) + 1  # 0-based to 1-based
        rect = ph.get("rect", [0, 0, 0, 0])
        
        print(f"{i:2d}. Key: '{key}' | Pattern: '{pattern}' | Page: {page}")
        print(f"    Position: ({rect[0]:.1f}, {rect[1]:.1f}) - ({rect[2]:.1f}, {rect[3]:.1f})")
        
        if key.lower() == "sitead":
            sitead_count += 1
            print(f"    🎯 SITEAD #{sitead_count} BULUNDU!")
        
        print()
    
    print(f"📊 SITEAD placeholder sayısı: {sitead_count}")
    
    # 4. Test doldurma ile problem testi
    print(f"\n🧪 PROBLEM TESPİT TESTİ:")
    print("-" * 30)
    
    # Test değerleri
    test_values = {}
    for ph in placeholders:
        key = ph.get("key", "")
        if key.lower() == "sitead":
            test_values[key] = "TEST_SITE_ADI"
        elif key:  # Diğer keyleri de test et
            test_values[key] = f"TEST_{key.upper()}"
    
    print(f"📝 Test değerleri: {test_values}")
    
    # API ile doldurma testi
    fill_request = {
        "session_id": session_id,
        "values": test_values,
        "font_size_mode": "auto",
        "allow_overflow": False
    }
    
    response = requests.post(f"{BASE_URL}/api/fill", json=fill_request)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("success"):
            print(f"✅ Doldurma testi başarılı!")
            print(f"📄 Download URL: {BASE_URL}/api/download/{session_id}")
        else:
            print(f"❌ Doldurma testi başarısız: {result.get('message')}")
    else:
        print(f"❌ Doldurma testi HTTP hatası: {response.status_code}")
    
    # 5. Temizlenmiş PDF'yi kontrol et
    print(f"\n🧹 TEMİZLENMİŞ PDF KONTROLÜ:")
    print("-" * 30)
    print(f"🔗 Temizlenmiş PDF önizleme: {BASE_URL}/api/preview/{session_id}?cleaned=true")
    print(f"🔗 Doldurulmuş PDF önizleme: {BASE_URL}/api/preview/{session_id}")
    
    return session_id, placeholders

def check_new_text_problem():
    """NEW yazısı problemini detaylı analiz eder"""
    print(f"\n🔍 'NEW' METNİ PROBLEMİ ANALİZİ:")
    print("-" * 30)
    print("Problem: 'NEW' yazısı placeholder olmadığı halde silinmiş")
    print("Sebep: Muhtemelen pattern matching'de aşırı geniş tespit")
    print("Çözüm: Pattern filtreleme algoritmasını optimize etmek gerekli")

if __name__ == "__main__":
    session_id, placeholders = analyze_ornek_pdf()
    check_new_text_problem()
    
    print(f"\n🎉 ANALİZ TAMAMLANDI!")
    if session_id:
        print(f"📊 Session: {session_id}")
        print(f"🌐 Web Interface: http://localhost:8011")
