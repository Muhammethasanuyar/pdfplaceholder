#!/usr/bin/env python3
"""
🚧 Overflow Test - Alan Taşma Özelliği Test Sistemi

Bu test, yeni eklenen "allow_overflow" özelliğinin çalışıp çalışmadığını test eder.
"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8011"
TEST_PDF = "ai_sessions/test_form.pdf"

def test_overflow_feature():
    """Overflow özelliğini test eder"""
    
    print("🚧 OVERFLOW FEATURE TEST")
    print("=" * 50)
    
    # 1. PDF upload et
    print("📁 1. PDF uploading...")
    
    if not Path(TEST_PDF).exists():
        print(f"❌ Test PDF bulunamadı: {TEST_PDF}")
        return
    
    with open(TEST_PDF, 'rb') as f:
        files = {'file': f}
        response = requests.post(f"{BASE_URL}/api/analyze", files=files)
    
    if response.status_code != 200:
        print(f"❌ Upload hatası: {response.status_code}")
        return
    
    data = response.json()
    if not data.get("success"):
        print(f"❌ Analiz hatası: {data.get('message')}")
        return
    
    session_id = data["session_id"]
    placeholders = data["placeholders"]
    
    print(f"✅ PDF uploaded successfully!")
    print(f"📊 Session ID: {session_id}")
    print(f"🎯 Placeholders found: {len(placeholders)}")
    
    # Test verileri - uzun metin kullan
    test_values = {}
    for ph in placeholders[:2]:  # İlk 2 placeholder'ı test et
        test_values[ph["key"]] = f"ÇOOOOK UZUN METİN {ph['key']} TEST ALAN TAŞMA"
    
    print(f"📝 Test values (long text): {test_values}")
    
    # 2. Overflow karşılaştırması
    test_scenarios = [
        {
            "name": "🚫 NORMAL MODE (Overflow YOK)",
            "data": {
                "session_id": session_id,
                "values": test_values,
                "font_size_mode": "fixed",
                "fixed_font_size": 30.0,
                "allow_overflow": False
            }
        },
        {
            "name": "🚧 OVERFLOW MODE (Taşma İZİNLİ)",
            "data": {
                "session_id": session_id,
                "values": test_values,
                "font_size_mode": "fixed",
                "fixed_font_size": 30.0,
                "allow_overflow": True
            }
        }
    ]
    
    print(f"\n🧪 TESTING OVERFLOW FEATURE:")
    print("=" * 40)
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{i}. {scenario['name']}")
        print("-" * 30)
        
        # API call
        response = requests.post(f"{BASE_URL}/api/fill", json=scenario["data"])
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"✅ SUCCESS: {result.get('message')}")
                print(f"📄 Download URL: {BASE_URL}/api/download/{session_id}")
            else:
                print(f"❌ FAIL: {result.get('message')}")
        else:
            print(f"❌ HTTP ERROR: {response.status_code}")
            try:
                print(f"   Detail: {response.json()}")
            except:
                print(f"   Raw: {response.text}")
        
        time.sleep(2)  # Sonuçları görmek için bekleme
    
    print(f"\n🎉 OVERFLOW FEATURE TEST COMPLETE!")
    print(f"📄 Test PDF: {TEST_PDF}")
    print(f"🔗 Son Preview URL: {BASE_URL}/api/preview/{session_id}")
    print(f"⬇️ Son Download URL: {BASE_URL}/api/download/{session_id}")

if __name__ == "__main__":
    test_overflow_feature()
