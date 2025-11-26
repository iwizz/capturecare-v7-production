#!/usr/bin/env python3
"""
Assign distinct, visually different colors to practitioners
Uses a curated palette of colors that are easily distinguishable
"""

import sqlite3
import os

# Get database path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(base_dir, 'capturecare', 'instance', 'capturecare.db')

if not os.path.exists(db_path):
    print(f"❌ Database not found at: {db_path}")
    exit(1)

# Curated palette of distinct colors (hex codes)
# These colors are chosen to be easily distinguishable from each other
DISTINCT_COLORS = [
    '#3B82F6',  # Blue
    '#10B981',  # Green
    '#F59E0B',  # Amber/Orange
    '#EF4444',  # Red
    '#8B5CF6',  # Purple
    '#EC4899',  # Pink
    '#06B6D4',  # Cyan
    '#84CC16',  # Lime
    '#F97316',  # Orange
    '#6366F1',  # Indigo
    '#14B8A6',  # Teal
    '#DC2626',  # Dark Red
    '#7C3AED',  # Violet
    '#059669',  # Emerald
    '#0EA5E9',  # Sky Blue
]

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all active practitioners
cursor.execute("SELECT id, first_name, last_name, calendar_color FROM users WHERE is_active = 1 ORDER BY id")
practitioners = cursor.fetchall()

if not practitioners:
    print("❌ No active practitioners found!")
    conn.close()
    exit(1)

print(f"📋 Found {len(practitioners)} active practitioners\n")

# Assign colors
updated_count = 0
for idx, (pract_id, first_name, last_name, current_color) in enumerate(practitioners):
    full_name = f"{first_name} {last_name}"
    
    # Get color from palette (cycle if more practitioners than colors)
    new_color = DISTINCT_COLORS[idx % len(DISTINCT_COLORS)]
    
    # Only update if color is default or too similar to others
    if current_color in ['#00698f', '#10b981', None, ''] or current_color == new_color:
        cursor.execute("UPDATE users SET calendar_color = ? WHERE id = ?", (new_color, pract_id))
        updated_count += 1
        print(f"✅ {full_name}: {current_color or 'None'} → {new_color}")
    else:
        print(f"⊙ {full_name}: Keeping existing color {current_color}")

conn.commit()
conn.close()

print(f"\n📊 Summary: {updated_count} practitioners updated with distinct colors")
print("✅ Done! Colors assigned successfully!")


