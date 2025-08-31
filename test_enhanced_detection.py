"""
Enhanced detection sistemini test et
"""
import fitz
from perfect_system import detect_placeholders_perfect

def test_enhanced_detection():
    """Enhanced detection sistemini test et"""
    print("🔍 TESTING ENHANCED PLACEHOLDER DETECTION")
    print("="*50)
    
    # Test PDF'ini aç
    doc = fitz.open("test_multi_pattern.pdf")
    
    # Enhanced detection'ı çalıştır
    placeholders = detect_placeholders_perfect(doc)
    
    print("\n📊 DETECTION RESULTS:")
    print("="*30)
    
    if placeholders:
        # Pattern türlerine göre grupla
        by_pattern = {}
        for ph in placeholders:
            pattern = ph.get('pattern', 'Unknown')
            if pattern not in by_pattern:
                by_pattern[pattern] = []
            by_pattern[pattern].append(ph)
        
        # Her pattern türünü göster
        for pattern, phs in by_pattern.items():
            print(f"\n🎯 Pattern: {pattern}")
            for ph in phs:
                print(f"   📍 Key: '{ph['key']}' | Text: '{ph['text']}'")
        
        print(f"\n✅ Total detected: {len(placeholders)} placeholders")
        print(f"🎨 Pattern varieties: {len(by_pattern)}")
        
        # En başarılı pattern'leri göster
        print("\n🏆 DETECTION SUCCESS:")
        for pattern in sorted(by_pattern.keys()):
            count = len(by_pattern[pattern])
            print(f"   {pattern}: {count} detected")
            
    else:
        print("❌ No placeholders detected!")
    
    doc.close()

if __name__ == "__main__":
    test_enhanced_detection()
