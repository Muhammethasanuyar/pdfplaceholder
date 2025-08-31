import sys
sys.path.append('.')

from perfect_system import detect_placeholders_perfect, physically_remove_placeholders
import fitz

def test_direct_optimization():
    """Optimize edilmiş fonksiyonları direkt test et"""
    print("🧪 DIRECT OPTİMİZASYON TESTİ")
    print("=" * 50)
    
    # 1) PDF aç
    pdf_path = "ornek_yeni.pdf"
    doc = fitz.open(pdf_path)
    
    print(f"📄 Test PDF: {pdf_path}")
    
    # 2) Placeholder detection test
    print(f"\n🎯 PLACEHOLDER DETECTION:")
    placeholders = detect_placeholders_perfect(doc)
    
    print(f"\n📊 SONUÇLAR:")
    print(f"   Total placeholder: {len(placeholders)}")
    
    # Key bazında grupla
    by_key = {}
    for ph in placeholders:
        key = ph['key']
        by_key.setdefault(key, []).append(ph)
    
    for key, instances in by_key.items():
        print(f"   📍 '{key}': {len(instances)} instance")
        for i, ph in enumerate(instances, 1):
            rect = ph['rect']
            print(f"      #{i} - '{ph['text']}' @ ({rect[0]:.1f}, {rect[1]:.1f})")
    
    # 3) NEW text overlap kontrolü
    print(f"\n🚨 NEW TEXT OVERLAP KONTROLÜ:")
    new_rect = [164.3, 138.3, 429.7, 256.1]  # NEW metninin pozisyonu
    
    overlapping_placeholders = []
    for ph in placeholders:
        ph_rect = ph['rect']
        # Overlap kontrolü
        if (ph_rect[0] < new_rect[2] and ph_rect[2] > new_rect[0] and 
            ph_rect[1] < new_rect[3] and ph_rect[3] > new_rect[1]):
            overlapping_placeholders.append(ph)
            print(f"   ❌ OVERLAP: '{ph['key']}' = '{ph['text']}'")
            print(f"      Placeholder: ({ph_rect[0]:.1f}, {ph_rect[1]:.1f}) - ({ph_rect[2]:.1f}, {ph_rect[3]:.1f})")
            print(f"      NEW text:    ({new_rect[0]:.1f}, {new_rect[1]:.1f}) - ({new_rect[2]:.1f}, {new_rect[3]:.1f})")
    
    if not overlapping_placeholders:
        print("   ✅ NEW text ile overlap yok")
    
    # 4) Removal testi (kopya doc ile)
    print(f"\n🧹 REMOVAL TESTİ:")
    doc_copy = fitz.open(pdf_path)  # Yeni kopya
    
    print("   Original NEW text check:")
    new_before = doc_copy[0].search_for("NEW")
    print(f"      NEW instances before removal: {len(new_before)}")
    
    # Precise removal uygula
    doc_copy = physically_remove_placeholders(doc_copy, placeholders)
    
    print("   After removal NEW text check:")
    new_after = doc_copy[0].search_for("NEW")
    print(f"      NEW instances after removal: {len(new_after)}")
    
    if len(new_after) == len(new_before):
        print("   ✅ NEW text korundu!")
    else:
        print("   ❌ NEW text silindi!")
    
    # Test dosyası kaydet
    test_cleaned_path = "test_cleaned_optimized.pdf"
    doc_copy.save(test_cleaned_path)
    print(f"   💾 Test cleaned PDF saved: {test_cleaned_path}")
    
    doc.close()
    doc_copy.close()
    
    return {
        'placeholders': len(placeholders),
        'sitead_count': len(by_key.get('sitead', [])),
        'oran_count': len(by_key.get('oran', [])),
        'new_preserved': len(new_after) == len(new_before),
        'overlapping_placeholders': len(overlapping_placeholders)
    }

if __name__ == "__main__":
    results = test_direct_optimization()
    print(f"\n🎉 TEST ÖZETİ:")
    print(f"   📊 Total placeholder: {results['placeholders']}")
    print(f"   🎯 Sitead instances: {results['sitead_count']}")
    print(f"   🎯 Oran instances: {results['oran_count']}")
    print(f"   🚨 NEW text preserved: {'✅' if results['new_preserved'] else '❌'}")
    print(f"   ⚠️ Overlapping placeholders: {results['overlapping_placeholders']}")
