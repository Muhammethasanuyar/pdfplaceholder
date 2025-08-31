import requests
import json

def test_optimized_system():
    """Optimize edilmiş sistemi test et"""
    print("🧪 OPTİMİZE EDİLMİŞ SİSTEM TESTİ")
    print("=" * 50)
    
    # 1) Upload PDF
    print("📤 UPLOAD TEST:")
    with open("ornek_yeni.pdf", "rb") as f:
        response = requests.post(
            "http://localhost:8011/api/upload",
            files={"file": ("ornek.pdf", f, "application/pdf")}
        )
    
    if response.status_code == 200:
        data = response.json()
        session_id = data["session_id"]
        placeholders = data["placeholders"]
        
        print(f"✅ Upload başarılı! Session ID: {session_id}")
        print(f"📊 Tespit edilen placeholder sayısı: {len(placeholders)}")
        
        # Placeholder detayları
        for i, ph in enumerate(placeholders, 1):
            rect = ph['rect']
            print(f"   📍 {i}. '{ph['key']}' = '{ph['text']}' @ ({rect[0]:.1f}, {rect[1]:.1f})")
            
        # sitead sayısını kontrol et
        sitead_count = sum(1 for ph in placeholders if ph['key'] == 'sitead')
        oran_count = sum(1 for ph in placeholders if ph['key'] == 'oran')
        
        print(f"\n📊 PLACEHOLDER ÖZETİ:")
        print(f"   🎯 sitead placeholder'ları: {sitead_count} adet")
        print(f"   🎯 oran placeholder'ları: {oran_count} adet")
        
        # 2) Fill test
        print(f"\n✍️ FILL TEST:")
        fill_data = {
            "session_id": session_id,
            "values": {
                "sitead": "OPTIMIZED_SITE",
                "oran": "50"
            },
            "font_size_mode": "auto",
            "allow_overflow": False
        }
        
        response = requests.post(
            "http://localhost:8011/api/fill",
            json=fill_data
        )
        
        if response.status_code == 200:
            print("✅ Fill başarılı!")
            print(f"📥 Download URL: http://localhost:8011/api/download/{session_id}")
            print(f"🔍 Preview URL: http://localhost:8011/api/preview/{session_id}")
            
            # 3) Temizlenmiş PDF'de NEW kontrolü
            print(f"\n🧹 CLEANED PDF KONTROLÜ:")
            try:
                clean_response = requests.get(f"http://localhost:8011/api/preview/{session_id}?cleaned=true")
                if clean_response.status_code == 200:
                    print("✅ Cleaned PDF erişilebilir")
                else:
                    print(f"❌ Cleaned PDF hata: {clean_response.status_code}")
            except Exception as e:
                print(f"❌ Cleaned PDF kontrolünde hata: {e}")
            
            print(f"\n🎉 TEST TAMAMLANDI!")
            print(f"🌐 Manuel kontrol için: http://localhost:8011")
            
            return session_id
        else:
            print(f"❌ Fill hatası: {response.status_code} - {response.text}")
    else:
        print(f"❌ Upload hatası: {response.status_code} - {response.text}")
    
    return None

if __name__ == "__main__":
    session_id = test_optimized_system()
    if session_id:
        print(f"\n🔗 Session files:")
        print(f"   Original: perfect_sessions/{session_id}_original.pdf")
        print(f"   Cleaned:  perfect_sessions/{session_id}_cleaned.pdf")
        print(f"   Filled:   perfect_sessions/{session_id}_filled.pdf")
