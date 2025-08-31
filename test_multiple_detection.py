"""
Multiple same-key detection test
"""
import fitz
from perfect_system import detect_placeholders_perfect

def test_multiple_same_key_detection():
    """Multiple same-key detection sistemini test et"""
    print("🔍 TESTING MULTIPLE SAME-KEY PLACEHOLDER DETECTION")
    print("="*60)
    
    # Test PDF'ini aç
    doc = fitz.open("test_multiple_same_key.pdf")
    
    # Enhanced detection'ı çalıştır
    placeholders = detect_placeholders_perfect(doc)
    
    print("\n📊 MULTIPLE SAME-KEY DETECTION RESULTS:")
    print("="*40)
    
    if placeholders:
        # Key'lere göre grupla
        by_key = {}
        for ph in placeholders:
            key = ph['key']
            if key not in by_key:
                by_key[key] = []
            by_key[key].append(ph)
        
        # Her key için instance'ları göster
        for key, instances in by_key.items():
            print(f"\n🎯 Key: '{key}' - {len(instances)} instances found")
            for i, ph in enumerate(instances, 1):
                rect = ph['rect']
                print(f"   📍 Instance {i}: '{ph['text']}' at ({rect[0]:.1f}, {rect[1]:.1f}) - Pattern: {ph.get('pattern', 'Unknown')}")
        
        print(f"\n✅ Total unique keys: {len(by_key)}")
        print(f"🎨 Total instances: {len(placeholders)}")
        
        # Expected vs Found karşılaştırması
        expected = {
            'Ad': 2,
            'Soyad': 3, 
            'Email': 1
        }
        
        print(f"\n🏆 RESULTS VERIFICATION:")
        for expected_key, expected_count in expected.items():
            found_count = len(by_key.get(expected_key, []))
            status = "✅ PASS" if found_count == expected_count else "❌ FAIL"
            print(f"   {expected_key}: Expected {expected_count}, Found {found_count} {status}")
            
    else:
        print("❌ No placeholders detected!")
    
    doc.close()

if __name__ == "__main__":
    test_multiple_same_key_detection()
