#!/usr/bin/env python3
"""
Add sample availability patterns for practitioners (max 7 hours per week each)
Simple version using direct database access
"""

import sqlite3
from datetime import time
import os

# Get database path
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(base_dir, 'capturecare', 'instance', 'capturecare.db')

if not os.path.exists(db_path):
    print(f"❌ Database not found at: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all active practitioners
cursor.execute("SELECT id, first_name, last_name, calendar_color FROM users WHERE is_active = 1")
practitioners = cursor.fetchall()

if not practitioners:
    print("❌ No active practitioners found!")
    conn.close()
    exit(1)

print(f"📋 Found {len(practitioners)} active practitioners\n")

# Sample availability patterns (max 7 hours per week)
# Format: (title, frequency, weekdays, start_time, end_time)
# NOTE: Some patterns overlap intentionally to show multiple practitioners available at same time
PATTERN_SETS = [
    [
        ("Monday Morning", "weekly", "0", "09:00", "12:00"),  # 3 hours - overlaps with set 5
        ("Wednesday Afternoon", "weekly", "2", "14:00", "17:00"),  # 3 hours
        ("Friday Morning", "weekly", "4", "10:00", "11:00"),  # 1 hour - overlaps with set 4
    ],
    [
        ("Tuesday Morning", "weekly", "1", "09:00", "12:00"),  # 3 hours - overlaps with set 3
        ("Thursday Afternoon", "weekly", "3", "13:00", "16:00"),  # 3 hours - overlaps with set 3
        ("Friday Afternoon", "weekly", "4", "14:00", "15:00"),  # 1 hour
    ],
    [
        ("Monday Afternoon", "weekly", "0", "13:00", "16:00"),  # 3 hours
        ("Tuesday Morning", "weekly", "1", "09:00", "12:00"),  # 3 hours - overlaps with set 2
        ("Thursday Afternoon", "weekly", "3", "13:00", "16:00"),  # 3 hours - overlaps with set 2
    ],
    [
        ("Tuesday Afternoon", "weekly", "1", "13:00", "16:00"),  # 3 hours
        ("Thursday Morning", "weekly", "3", "09:00", "12:00"),  # 3 hours
        ("Friday Morning", "weekly", "4", "10:00", "11:00"),  # 1 hour - overlaps with set 1
    ],
    [
        ("Monday Morning", "weekly", "0", "09:00", "12:00"),  # 3 hours - overlaps with set 1
        ("Wednesday Morning", "weekly", "2", "09:00", "12:00"),  # 3 hours - overlaps with set 5
        ("Friday Afternoon", "weekly", "4", "14:00", "16:00"),  # 2 hours
    ],
]

for idx, (pract_id, first_name, last_name, color) in enumerate(practitioners):
    full_name = f"{first_name} {last_name}"
    print(f"👤 Processing: {full_name} (ID: {pract_id})")
    
    # Check existing patterns
    cursor.execute("SELECT COUNT(*) FROM availability_patterns WHERE user_id = ? AND is_active = 1", (pract_id,))
    existing_count = cursor.fetchone()[0]
    
    if existing_count > 0:
        print(f"   ⚠️  {existing_count} existing patterns found. Skipping...\n")
        continue
    
    # Get pattern set for this practitioner (rotate through sets)
    pattern_set = PATTERN_SETS[idx % len(PATTERN_SETS)]
    patterns_created = 0
    
    for title, frequency, weekdays, start_str, end_str in pattern_set:
        # Parse times
        start_h, start_m = map(int, start_str.split(':'))
        end_h, end_m = map(int, end_str.split(':'))
        
        # Insert pattern
        cursor.execute("""
            INSERT INTO availability_patterns 
            (user_id, title, frequency, weekdays, start_time, end_time, is_active, color, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, datetime('now'), datetime('now'))
        """, (pract_id, title, frequency, weekdays, f"{start_h:02d}:{start_m:02d}:00", f"{end_h:02d}:{end_m:02d}:00", color))
        
        patterns_created += 1
        hours = end_h - start_h + (end_m - start_m) / 60
        print(f"   ✅ Created: {title} ({start_str}-{end_str}, {hours:.1f}h) - Day: {weekdays}")
    
    conn.commit()
    print(f"   📊 Total: {patterns_created} patterns created\n")

# Summary
print("📈 Summary:")
cursor.execute("""
    SELECT u.id, u.first_name || ' ' || u.last_name, COUNT(ap.id)
    FROM users u
    LEFT JOIN availability_patterns ap ON u.id = ap.user_id AND ap.is_active = 1
    WHERE u.is_active = 1
    GROUP BY u.id, u.first_name, u.last_name
""")
for pract_id, name, pattern_count in cursor.fetchall():
    print(f"   {name}: {pattern_count} patterns")

conn.close()
print("\n✅ Done! Sample availability patterns added successfully!")

