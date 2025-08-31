#!/usr/bin/env python3
"""
🎯 Font Size Control System Test

Bu test, yeni eklenen font boyutu kontrol sisteminin çalışıp çalışmadığını test eder.
"""

import requests
import json
import time
from pathlib import Path

BASE_URL = "http://localhost:8011"
TEST_PDF = "ai_sessions/test_form.pdf"

def test_font_size_modes():
    """Farklı font boyutu modlarını test eder"""
    
    print("🎯 FONT SIZE CONTROL SYSTEM TEST")
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
    
    # Test verileri
    test_values = {}
    for ph in placeholders[:3]:  # İlk 3 placeholder'ı test et
        test_values[ph["key"]] = f"Test_{ph['key']}"
    
    print(f"📝 Test values: {test_values}")
    
    # 2. Farklı font boyutu modlarını test et
    test_scenarios = [
        {
            "name": "🤖 AUTO MODE",
            "data": {
                "session_id": session_id,
                "values": test_values,
                "font_size_mode": "auto"
            }
        },
        {
            "name": "📌 FIXED MODE (16pt)",
            "data": {
                "session_id": session_id,
                "values": test_values,
                "font_size_mode": "fixed",
                "fixed_font_size": 16.0
            }
        },
        {
            "name": "📊 MIN/MAX MODE (10-20pt)",
            "data": {
                "session_id": session_id,
                "values": test_values,
                "font_size_mode": "min_max",
                "min_font_size": 10.0,
                "max_font_size": 20.0
            }
        }
    ]
    
    print("\n🧪 TESTING FONT SIZE MODES:")
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
            else:
                print(f"❌ FAIL: {result.get('message')}")
        else:
            print(f"❌ HTTP ERROR: {response.status_code}")
            try:
                print(f"   Detail: {response.json()}")
            except:
                print(f"   Raw: {response.text}")
        
        time.sleep(1)  # Küçük gecikme
    
    print(f"\n🎉 FONT SIZE CONTROL TEST COMPLETE!")
    print(f"📄 Test PDF: {TEST_PDF}")
    print(f"🔗 Preview URL: {BASE_URL}/api/preview/{session_id}")
    print(f"⬇️ Download URL: {BASE_URL}/api/download/{session_id}")

if __name__ == "__main__":
    test_font_size_modes()
