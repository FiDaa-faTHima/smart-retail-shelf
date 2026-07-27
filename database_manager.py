import sqlite3
import os
import json
import cv2 # 📸 Needed to save the JPG image to your hard drive
from datetime import datetime

DB_NAME = "retail.db"
IMAGE_DIR = os.path.join('static', 'detections')

# Ensure the detections folder exists
os.makedirs(IMAGE_DIR, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 🔐 1. Login System
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # 🗺️ 2. AI Map
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shelf_map (
            id INTEGER PRIMARY KEY,
            zone_name TEXT, 
            product_id INTEGER, 
            x1 INTEGER, y1 INTEGER, x2 INTEGER, y2 INTEGER, 
            max_capacity INTEGER 
        )
    ''')

    # 🚨 3. Alerts Table (NOW WITH SNAPSHOT PATH)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shelf_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT DEFAULT 'CAM_01',
            region_id TEXT,             
            region_location TEXT,       
            product_name TEXT,          
            product_count INTEGER,      
            void_percentage INTEGER,    
            alert_type TEXT,            
            snapshot_path TEXT,         -- 📸 File path to annotated JPG
            timestamp DATETIME
        )
    ''')

    # 🟢 4. Normal Table (NOW WITH SNAPSHOT PATH)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shelf_normal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id TEXT DEFAULT 'CAM_01',
            shelf_id TEXT,              
            product_name TEXT,
            product_count INTEGER,
            status TEXT DEFAULT 'Normal',
            snapshot_path TEXT,         -- 📸 File path to annotated JPG
            timestamp DATETIME
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database with Image Tracking initialized successfully!")


def log_smart_shelf_scans(dashboard_data, learned_regions, annotated_frame):
    """
    Saves live telemetry metrics AND physical cropped JPEG snapshots to local storage and DB.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now()
        timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
        file_timestamp = now.strftime('%Y%m%d_%H%M%S')

        for zone in dashboard_data:
            region_specs = next((r for r in learned_regions if (learned_regions.index(r) + 1) == zone['zone_id']), None)
            
            region_coords = ""
            image_filename = ""
            saved_path = ""

            if region_specs:
                x1, y1, x2, y2 = region_specs['x1'], region_specs['y1'], region_specs['x2'], region_specs['y2']
                region_coords = json.dumps([x1, y1, x2, y2])

                # ✂️ Crop the YOLO frame to just the Shelf Region
                try:
                    cropped_img = annotated_frame[y1:y2, x1:x2]
                    
                    # Create a clean filename (e.g., Zone1_LowStock_20260322_1845.jpg)
                    clean_status = "".join(c for c in zone['status'] if c.isalnum())
                    image_filename = f"Zone{zone['zone_id']}_{clean_status}_{file_timestamp}.jpg"
                    saved_path = os.path.join(IMAGE_DIR, image_filename)

                    # Write the image to /static/detections/
                    cv2.imwrite(saved_path, cropped_img)
                except Exception as e:
                    print(f"⚠️ Could not crop region {zone['zone_id']}: {e}")

            # 🚨 Branch A: Alerts
            if "Low Stock" in zone['status'] or "Mismatch" in zone['status'] or "Stockout" in zone['status']:
                cursor.execute('''
                    INSERT INTO shelf_alerts (camera_id, region_id, region_location, product_name, product_count, void_percentage, alert_type, snapshot_path, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', ('CAM_01', f"Zone {zone['zone_id']}", region_coords, zone['expected_item'], 0 if "Stockout" in zone['status'] else 1, zone['void_ratio'], zone['status'], saved_path, timestamp_str))

            # 🟢 Branch B: Normal Scan
            else:
                cursor.execute('''
                    INSERT INTO shelf_normal_logs (camera_id, shelf_id, product_name, product_count, status, snapshot_path, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ('CAM_01', f"Zone {zone['zone_id']}", zone['expected_item'], 1, zone['status'], saved_path, timestamp_str))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"❌ Smart Retail Logging Error: {e}")
        return False