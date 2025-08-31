import fitz
import re
from typing import List, Dict, Set, Tuple

def analyze_false_positive_patterns(pdf_path: str):
    """False positive pattern detection'ları tespit et"""
    print("🔍 FALSE POSITIVE PATTERN ANALYSIS")
    print("=" * 50)
    
    doc = fitz.open(pdf_path)
    
    # Current patterns (from perfect_system.py)
    PH_PATTERNS = [
        re.compile(r'\{\{\s*([^}]+?)\s*\}\}'),      # {{Ad}}
        re.compile(r'\{\s*\{\s*([^}]+?)\s*\}\s*\}'), # { {Ad} }
        re.compile(r'\{\s*([^}]+?)\s*\}'),            # {Ad} - BU TEHLIKELI!
        re.compile(r'\[\[\s*([^\]]+?)\s*\]\]'),       # [[Ad]]
        re.compile(r'\[\s*\[\s*([^\]]+?)\s*\]\s*\]'), # [ [Ad] ]
        re.compile(r'\[\s*([^\]]+?)\s*\]'),            # [Ad] - BU DA TEHLIKELI!
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
    
    PATTERN_NAMES = [
        "{{Ad}}", "{ {Ad} }", "{Ad}", "[[Ad]]", "[ [Ad] ]", "[Ad]", 
        "((Ad))", "( (Ad) )", "{{{Ad}}}", "{[Ad]}", "[{Ad}]", 
        "${Ad}", "%{Ad}%", "@{Ad}", "#{Ad}"
    ]
    
    all_text = ""
    for page in doc:
        all_text += page.get_text() + "\n"
    
    print(f"📝 Total text length: {len(all_text)} chars")
    print("\n🎯 PATTERN MATCH RESULTS:")
    print("-" * 30)
    
    for i, pattern in enumerate(PH_PATTERNS):
        matches = list(pattern.finditer(all_text))
        pattern_name = PATTERN_NAMES[i]
        
        print(f"\n📍 Pattern {i+1}: {pattern_name}")
        print(f"   Matches found: {len(matches)}")
        
        for j, match in enumerate(matches):
            full_match = match.group(0)
            key = match.group(1).strip()
            context_start = max(0, match.start() - 20)
            context_end = min(len(all_text), match.end() + 20)
            context = all_text[context_start:context_end].replace('\n', ' ').strip()
            
            # FALSE POSITIVE CHECKS
            is_false_positive = False
            reasons = []
            
            # 1) Sadece büyük harf + digit (like "NEW", "123") 
            if key.isalnum() and (key.isupper() or key.isdigit()) and len(key) <= 4:
                is_false_positive = True
                reasons.append(f"Short uppercase/digit: '{key}'")
            
            # 2) Common words (Turkish/English)
            common_words = {'NEW', 'OLD', 'YES', 'NO', 'TOP', 'END', 'ALL', 'ANY'}
            if key.upper() in common_words:
                is_false_positive = True
                reasons.append(f"Common word: '{key}'")
            
            # 3) Single characters
            if len(key) == 1:
                is_false_positive = True
                reasons.append(f"Single char: '{key}'")
            
            # 4) Numbers only
            if key.isdigit():
                is_false_positive = True
                reasons.append(f"Number only: '{key}'")
                
            status = "❌ FALSE POSITIVE" if is_false_positive else "✅ VALID"
            
            print(f"   [{j+1}] '{full_match}' → key: '{key}' {status}")
            if is_false_positive:
                print(f"       Reasons: {', '.join(reasons)}")
            print(f"       Context: ...{context}...")
    
    doc.close()
    
    print(f"\n💡 RECOMMENDATIONS:")
    print("1. Disable risky patterns: {Ad} and [Ad] (patterns 3 and 6)")
    print("2. Add length filters: key must be >= 2 chars")
    print("3. Add word filters: exclude common words")
    print("4. Add character filters: exclude pure numbers/uppercase")

if __name__ == "__main__":
    analyze_false_positive_patterns("perfect_sessions/0e28a84a-ffdb-44dc-8674-39a5aa4e6c2c_original.pdf")
