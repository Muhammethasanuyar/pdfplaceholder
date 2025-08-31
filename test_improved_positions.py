#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMPROVED PLACEHOLDER SYSTEM - Multiple Positions per Key Support
"""

import fitz
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

def detect_placeholders_with_positions(doc: fitz.Document) -> List[Dict]:
    """Enhanced placeholder detection with position-based unique keys"""
    print("🔍 POSITION-BASED PLACEHOLDER DETECTION")
    
    # Supported patterns
    patterns = [
        (r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}', "{{Ad}}"),
        (r'\[\[([A-Za-z_][A-Za-z0-9_]*)\]\]', "[[Ad]]"),
        (r'\{([A-Za-z_][A-Za-z0-9_]*)\}', "{Ad}"),
        (r'\[([A-Za-z_][A-Za-z0-9_]*)\]', "[Ad]"),
        (r'%([A-Za-z_][A-Za-z0-9_]*)%', "%Ad%"),
        (r'@([A-Za-z_][A-Za-z0-9_]*)@', "@Ad@"),
        (r'#([A-Za-z_][A-Za-z0-9_]*)#', "#Ad#"),
    ]
    
    placeholders = []
    processed_rects = set()
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        print(f"📄 Page {page_num + 1}")
        
        for pattern_re, pattern_name in patterns:
            page_text = page.get_text()
            matches = re.finditer(pattern_re, page_text)
            
            for match in matches:
                base_key = match.group(1).strip()
                full_match = match.group(0)
                
                # Find all visual instances
                instances = page.search_for(full_match)
                
                for rect in instances:
                    # Skip if already processed
                    rect_key = (page_num, round(rect.x0, 1), round(rect.y0, 1))
                    if rect_key in processed_rects:
                        continue
                    
                    processed_rects.add(rect_key)
                    
                    # Get context for better identification
                    try:
                        expanded = fitz.Rect(rect.x0-40, rect.y0-8, rect.x1+40, rect.y1+8)
                        context = page.get_textbox(expanded).strip()
                        context = context.replace('\n', ' ').replace('\r', ' ')
                    except:
                        context = ""
                    
                    placeholder = {
                        'base_key': base_key,
                        'text': full_match,
                        'pattern': pattern_name,
                        'page': page_num,
                        'rect': [rect.x0, rect.y0, rect.x1, rect.y1],
                        'context': context,
                        'font_size': rect.height * 0.6  # Estimate
                    }
                    
                    placeholders.append(placeholder)
                    print(f"   ✅ Found '{full_match}' at ({rect.x0:.1f}, {rect.y0:.1f})")
    
    # Group by base_key and assign position indexes
    key_groups = {}
    for ph in placeholders:
        base_key = ph['base_key']
        if base_key not in key_groups:
            key_groups[base_key] = []
        key_groups[base_key].append(ph)
    
    # Assign unique keys
    final_placeholders = []
    for base_key, group in key_groups.items():
        # Sort by Y position (top to bottom), then X (left to right)
        group.sort(key=lambda p: (p['rect'][1], p['rect'][0]))
        
        for i, ph in enumerate(group):
            if len(group) == 1:
                # Single instance - keep original key
                unique_key = base_key
                display_name = base_key
            else:
                # Multiple instances - add position index
                unique_key = f"{base_key}_{i+1}"
                context_preview = ph['context'][:25] + '...' if len(ph['context']) > 25 else ph['context']
                display_name = f"{base_key} #{i+1}" + (f" ({context_preview})" if context_preview else "")
            
            ph['unique_key'] = unique_key
            ph['display_name'] = display_name
            final_placeholders.append(ph)
            
            print(f"   🎯 Assigned: '{unique_key}' -> '{display_name}'")
    
    print(f"🎯 Detection complete: {len(final_placeholders)} positioned placeholders")
    return final_placeholders

def create_position_based_form(placeholders: List[Dict]) -> Dict[str, Any]:
    """Create form data structure for frontend with position-based fields"""
    
    form_data = {
        'placeholders': [],
        'field_groups': {}
    }
    
    # Group placeholders by base key
    base_groups = {}
    for ph in placeholders:
        base_key = ph['base_key']
        if base_key not in base_groups:
            base_groups[base_key] = []
        base_groups[base_key].append(ph)
    
    for base_key, group in base_groups.items():
        if len(group) == 1:
            # Single field
            ph = group[0]
            form_data['placeholders'].append({
                'id': ph['unique_key'],
                'name': ph['display_name'],
                'type': 'text',
                'placeholder': f"Enter value for {base_key}",
                'context': ph.get('context', ''),
                'position': f"Page {ph['page'] + 1}, ({ph['rect'][0]:.0f}, {ph['rect'][1]:.0f})"
            })
        else:
            # Multiple positions - create group
            form_data['field_groups'][base_key] = {
                'label': f"{base_key} (Multiple Positions)",
                'description': f"This placeholder appears in {len(group)} different positions",
                'fields': []
            }
            
            for ph in group:
                form_data['field_groups'][base_key]['fields'].append({
                    'id': ph['unique_key'],
                    'name': ph['display_name'],
                    'type': 'text',
                    'placeholder': f"Enter value for position {ph['unique_key'].split('_')[-1]}",
                    'context': ph.get('context', ''),
                    'position': f"Page {ph['page'] + 1}, ({ph['rect'][0]:.0f}, {ph['rect'][1]:.0f})"
                })
    
    return form_data

def fill_position_based_placeholders(doc: fitz.Document, placeholders: List[Dict], values: Dict[str, str]) -> fitz.Document:
    """Fill placeholders using position-based keys"""
    print(f"🖊️ POSITION-BASED FILLING: {len(values)} values")
    
    # Create a mapping from unique_key to placeholder
    key_to_placeholder = {ph['unique_key']: ph for ph in placeholders}
    
    filled_count = 0
    
    for unique_key, value in values.items():
        if not value or unique_key not in key_to_placeholder:
            continue
        
        ph = key_to_placeholder[unique_key]
        page = doc[ph['page']]
        rect = fitz.Rect(*ph['rect'])
        
        # Calculate font size based on rect height
        font_size = min(rect.height * 0.7, 24.0)
        font_size = max(font_size, 8.0)
        
        print(f"   📝 Filling '{unique_key}' with '{value}' at {rect}")
        
        try:
            # Clear the area first (optional)
            # page.add_redact_annot(rect)
            # page.apply_redactions()
            
            # Insert new text
            result = page.insert_textbox(
                rect,
                value,
                fontname="helv",
                fontsize=font_size,
                align=fitz.TEXT_ALIGN_CENTER,
                color=(0, 0, 0)
            )
            
            if result >= 0:
                print(f"   ✅ Success: '{unique_key}' filled")
                filled_count += 1
            else:
                print(f"   ⚠️ Overflow: '{unique_key}' text too long")
                
        except Exception as e:
            print(f"   ❌ Error filling '{unique_key}': {e}")
    
    print(f"🎯 Filling complete: {filled_count} placeholders filled")
    return doc

def improved_coordinate_placement(doc: fitz.Document, placeholders: List[Dict], values: Dict[str, str]) -> fitz.Document:
    """Enhanced coordinate-based placement system"""
    print(f"🎯 IMPROVED COORDINATE PLACEMENT")
    
    for ph in placeholders:
        unique_key = ph['unique_key']
        if unique_key not in values or not values[unique_key]:
            continue
            
        value = values[unique_key]
        page = doc[ph['page']]
        
        # Get original rect
        orig_rect = fitz.Rect(*ph['rect'])
        
        # IMPROVED RECT CALCULATION
        # Method 1: Use exact search position
        search_results = page.search_for(ph['text'])
        if search_results:
            # Find closest match to original detection
            best_rect = None
            min_distance = float('inf')
            
            for search_rect in search_results:
                distance = abs(search_rect.x0 - orig_rect.x0) + abs(search_rect.y0 - orig_rect.y0)
                if distance < min_distance:
                    min_distance = distance
                    best_rect = search_rect
            
            if best_rect:
                # Use the exact found position
                final_rect = fitz.Rect(best_rect)
                
                # Expand rect slightly for better fit
                padding = 2.0
                final_rect.x0 -= padding
                final_rect.y0 -= padding
                final_rect.x1 += padding * 2
                final_rect.y1 += padding
                
                print(f"   📐 Using exact search rect for '{unique_key}': {final_rect}")
            else:
                final_rect = orig_rect
        else:
            final_rect = orig_rect
        
        # Font size calculation
        font_size = min(final_rect.height * 0.75, 20.0)
        font_size = max(font_size, 6.0)
        
        # Remove original placeholder first
        try:
            placeholder_rects = page.search_for(ph['text'])
            for pr in placeholder_rects:
                # Only remove if close to our target position
                if abs(pr.x0 - final_rect.x0) < 5 and abs(pr.y0 - final_rect.y0) < 5:
                    page.add_redact_annot(pr)
            page.apply_redactions()
        except Exception as e:
            print(f"   ⚠️ Could not remove placeholder '{ph['text']}': {e}")
        
        # Insert new text
        try:
            result = page.insert_textbox(
                final_rect,
                value,
                fontname="helv",
                fontsize=font_size,
                align=fitz.TEXT_ALIGN_LEFT,  # Try left alignment for better positioning
                color=(0, 0, 0)
            )
            
            print(f"   ✅ Placed '{unique_key}': '{value}' at {final_rect} (size: {font_size:.1f}pt, result: {result})")
            
        except Exception as e:
            print(f"   ❌ Failed to place '{unique_key}': {e}")
    
    return doc

if __name__ == "__main__":
    # Test with available PDF
    test_files = [
        "perfect_sessions/9ac1df93-8a55-4cc7-8915-db13e33aef73_original.pdf",
        "perfect_sessions/928e2d80-d168-43b0-8976-1a521db45248_original.pdf", 
        "perfect_sessions/6fccf4f5-cdb6-44bb-b6f6-833f6af08427_original.pdf",
        "perfect_sessions/051bdbb4-85e4-4cf7-97e2-63a5a41b5592_original.pdf",
        "Ornek.pdf", "Ornek (1).pdf", "Ornek (2).pdf", "ai_sessions/test_form.pdf"
    ]
    
    test_file = None
    for f in test_files:
        if Path(f).exists():
            test_file = f
            break
    
    if not test_file:
        print("❌ No test file found")
        exit(1)
    
    print(f"📄 Testing with: {test_file}")
    
    # Test detection
    doc = fitz.open(test_file)
    placeholders = detect_placeholders_with_positions(doc)
    
    # Create form structure
    form_data = create_position_based_form(placeholders)
    
    print(f"\n📋 FORM STRUCTURE:")
    print(f"   Single fields: {len(form_data['placeholders'])}")
    print(f"   Field groups: {len(form_data['field_groups'])}")
    
    for group_key, group_data in form_data['field_groups'].items():
        print(f"   📁 {group_data['label']}: {len(group_data['fields'])} positions")
        for field in group_data['fields']:
            print(f"      - {field['name']}: {field['position']}")
    
    # Test filling with sample data
    sample_values = {}
    for ph in placeholders:
        if 'sitead' in ph['unique_key']:
            sample_values[ph['unique_key']] = f"TestSite{ph['unique_key'].split('_')[-1] if '_' in ph['unique_key'] else ''}"
        elif 'oran' in ph['unique_key']:
            sample_values[ph['unique_key']] = "85"
    
    print(f"\n🧪 SAMPLE VALUES:")
    for key, value in sample_values.items():
        print(f"   {key}: {value}")
    
    # Test improved placement
    doc_filled = improved_coordinate_placement(doc, placeholders, sample_values)
    
    output_path = "test_improved_positions.pdf"
    doc_filled.save(output_path)
    doc.close()
    
    print(f"\n💾 Test output saved: {output_path}")
