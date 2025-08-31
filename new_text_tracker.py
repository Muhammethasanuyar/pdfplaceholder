import fitz
import requests
import json

def track_new_text_problem():
    """NEW metninin neden silindiğini bul"""
    print("🔍 NEW TEXT PROBLEM TRACKER")
    print("=" * 40)
    
    session_id = "0e28a84a-ffdb-44dc-8674-39a5aa4e6c2c"
    
    # 1) Original PDF'de NEW pozisyonu
    original_path = f"perfect_sessions/{session_id}_original.pdf"
    original_doc = fitz.open(original_path)
    
    print("📄 ORIGINAL PDF - NEW TEXT LOCATIONS:")
    new_locations = []
    for page_num, page in enumerate(original_doc):
        new_instances = page.search_for("NEW")
        for i, rect in enumerate(new_instances):
            print(f"   NEW #{i+1} at page {page_num+1}: ({rect.x0:.1f}, {rect.y0:.1f}) - ({rect.x1:.1f}, {rect.y1:.1f})")
            new_locations.append({
                'page': page_num,
                'rect': [rect.x0, rect.y0, rect.x1, rect.y1],
                'index': i
            })
    
    original_doc.close()
    
    # 2) Server'dan detected placeholder'ları al
    print(f"\n🎯 PLACEHOLDER DETECTION ANALYSIS:")
    try:
        response = requests.get(f"http://localhost:8011/api/placeholders/{session_id}")
        if response.status_code == 200:
            data = response.json()
            placeholders = data.get('placeholders', [])
            print(f"   Detected placeholders: {len(placeholders)}")
            
            # NEW ile overlap eden placeholder var mı?
            for new_loc in new_locations:
                new_rect = new_loc['rect']
                print(f"\n📍 Checking NEW at ({new_rect[0]:.1f}, {new_rect[1]:.1f}):")
                
                overlapping = []
                for ph in placeholders:
                    ph_rect = ph['rect']
                    
                    # Overlap kontrolü (basit rectangular intersection)
                    if (new_rect[0] < ph_rect[2] and new_rect[2] > ph_rect[0] and 
                        new_rect[1] < ph_rect[3] and new_rect[3] > ph_rect[1]):
                        overlapping.append(ph)
                        print(f"   ❌ OVERLAP with placeholder: '{ph['key']}' = '{ph['text']}' at ({ph_rect[0]:.1f}, {ph_rect[1]:.1f})")
                
                if not overlapping:
                    print(f"   ✅ No overlapping placeholders found")
    
    except Exception as e:
        print(f"❌ Error checking placeholders: {e}")
    
    # 3) Cleaned PDF'de NEW var mı kontrol et
    print(f"\n🧹 CLEANED PDF CHECK:")
    cleaned_path = f"perfect_sessions/{session_id}_cleaned.pdf"
    cleaned_doc = fitz.open(cleaned_path)
    
    for page_num, page in enumerate(cleaned_doc):
        new_instances = page.search_for("NEW")
        if new_instances:
            print(f"   ✅ NEW found on page {page_num+1}: {len(new_instances)} instances")
            for rect in new_instances:
                print(f"      Position: ({rect.x0:.1f}, {rect.y0:.1f}) - ({rect.x1:.1f}, {rect.y1:.1f})")
        else:
            print(f"   ❌ NEW NOT FOUND on page {page_num+1}")
    
    cleaned_doc.close()
    
    # 4) Manual pattern test on "NEW"
    print(f"\n🔍 MANUAL PATTERN TEST ON 'NEW':")
    import re
    test_text = "NEW"
    
    PH_PATTERNS = [
        re.compile(r'\{\{\s*([^}]+?)\s*\}\}'),      # {{Ad}}
        re.compile(r'\{\s*\{\s*([^}]+?)\s*\}\s*\}'), # { {Ad} }
        re.compile(r'\{\s*([^}]+?)\s*\}'),            # {Ad}
        re.compile(r'\[\[\s*([^\]]+?)\s*\]\]'),       # [[Ad]]
        re.compile(r'\[\s*\[\s*([^\]]+?)\s*\]\s*\]'), # [ [Ad] ]
        re.compile(r'\[\s*([^\]]+?)\s*\]'),            # [Ad]
        re.compile(r'\(\(\s*([^)]+?)\s*\)\)'),        # ((Ad))
        re.compile(r'\(\s*\(\s*([^)]+?)\s*\)\s*\)'),  # ( (Ad) )
        re.compile(r'\{\{\{\s*([^}]+?)\s*\}\}\}'),    # {{{Ad}}}
        re.compile(r'\{\[\s*([^\]]+?)\s*\]\}'),       # {[Ad]}
        re.compile(r'\[\{\s*([^}]+?)\s*\}\]'),        # [{Ad}]
        re.compile(r'\$\{\s*([^}]+?)\s*\}'),          # ${Ad}
        re.compile(r'%\{\s*([^}]+?)\s*\}%'),          # %{Ad}%
        re.compile(r'@\{\s*([^}]+?)\s*\}'),           # @{Ad}
        re.compile(r'#\{\s*([^}]+?)\s*\}'),           # #{Ad}
    ]
    
    for i, pattern in enumerate(PH_PATTERNS):
        matches = list(pattern.finditer(test_text))
        if matches:
            print(f"   Pattern {i+1} MATCHES 'NEW': {[m.group(0) for m in matches]}")
        else:
            print(f"   Pattern {i+1}: No match")

if __name__ == "__main__":
    track_new_text_problem()
