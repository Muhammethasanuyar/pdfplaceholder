#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re

# Emoji listesi - projedeki tüm emojiler
emojis_to_remove = [
    '🎯', '✨', '🇹🇷', '⚡', '🚀', '📱', '🔧', '📝', '❌', '⚠️', '✅', '🆘', 
    '📉', '📐', '🎨', '🔍', '🖨️', '💎', '📊', '🚧', '📏', '👤', '👁️', '🖥️', 
    '📋', '📄', '📎', '💻', '🌟', '🎭', '🎪', '🔥', '🌈', '🎉', '🏆', '🔊', 
    '📢', '🎵', '🎺', '🎸', '🎧', '🎤', '📻', '📺', '📼', '📹', '🎬', '🎥', 
    '📷', '📸', '🖼️', '🖌️', '🖍️', '✏️', '📰', '🗞️', '📃', '🗒️', '📑', 
    '🔖', '🏷️', '💰', '💴', '💵', '💶', '💷', '💸', '💳', '🧾', '💹', '💲', 
    '💱', '💽', '💾', '💿', '📀', '📲', '☎️', '📞', '📟', '📠', '🔋', '🔌', 
    '⌨️', '🖱️', '🖲️', '🔎', '🕯️', '💡', '🔦', '🏮', '🪔', '📌', '📍', 
    '🗂️', '📂', '📁', '🗃️', '🗄️', '🗑️', '🔒', '🔓', '🔏', '🔐', '🔑', 
    '🗝️', '🔨', '⛏️', '⚒️', '🛠️', '🗡️', '⚔️', '🔫', '🏹', '🛡️', '🔩', 
    '⚙️', '🗜️', '⚖️', '🦯', '🔗', '⛓️', '🧰', '🧲', '⚗️', '💾'
]

def remove_emojis_from_file(filepath):
    """Dosyadan emojileri kaldır"""
    print(f"Processing: {filepath}")
    
    # Dosyayı oku
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    original_content = content
    
    # Her emoji için değiştirme yap
    for emoji in emojis_to_remove:
        content = content.replace(emoji, '')
    
    # Gereksiz boşlukları temizle
    content = re.sub(r'  +', ' ', content)  # Çoklu boşlukları tek boşluğa çevir
    content = re.sub(r'^ ', '', content, flags=re.MULTILINE)  # Satır başındaki boşlukları kaldır
    
    # Değişiklik var mı kontrol et
    if content != original_content:
        # Dosyayı yaz
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Emojis removed from {filepath}")
        except Exception as e:
            print(f"Error writing file: {e}")
    else:
        print(f"- No emojis found in {filepath}")

if __name__ == "__main__":
    # perfect_system.py dosyasından emojileri kaldır
    remove_emojis_from_file('perfect_system.py')
    print("Emoji removal completed!")
