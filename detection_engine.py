import cv2
import numpy as np
from datetime import datetime
import os# 🧠 Autonomous Memory to store what the shelf "looked like" on Frame 1
learned_regions = [] 
is_calibrated = False

def calibrate_shelf_regions(frame, model):
    """
    🔬 RUNS ON FRAME 1 ONLY:
    Identifies identical products sitting near each other, groups them into 
    visual "Sub-Regions", and locks them in as the baseline.
    """
    global learned_regions, is_calibrated
    results = model(frame)[0]
    
    products = []
    
    for box in results.boxes:
        coords = box.xyxy[0].cpu().numpy().astype(int)
        cls_id = int(box.cls[0])
        label = model.names[cls_id]
        
        # Focus ONLY on products (not gaps or shelf frames)
        if cls_id not in [29, 30, 31, 38, 0, 37]: 
            products.append({'coords': coords, 'label': label, 'cls_id': cls_id})

    # Sort products Left-to-Right (X-axis) to detect adjacent neighbors
    products.sort(key=lambda p: p['coords'][0])

    current_region = None
    GAP_THRESHOLD = 150 # 📏 Max horizontal pixels allowed between neighbors before a "Split"

    for p in products:
        if current_region is None:
            # Start the very first sub-region
            current_region = {
                'label': p['label'],
                'cls_id': p['cls_id'],
                'x1': p['coords'][0], 'y1': p['coords'][1],
                'x2': p['coords'][2], 'y2': p['coords'][3],
                'count': 1
            }
        else:
            px1 = p['coords'][0]
            # If it's the SAME product and close enough, expand the current region
            if p['label'] == current_region['label'] and (px1 - current_region['x2']) < GAP_THRESHOLD:
                current_region['x2'] = max(current_region['x2'], p['coords'][2])
                current_region['y1'] = min(current_region['y1'], p['coords'][1])
                current_region['y2'] = max(current_region['y2'], p['coords'][3])
                current_region['count'] += 1
            else:
                # ✂️ Split Detected! Save the old region and start a new one for the next product
                learned_regions.append(current_region)
                current_region = {
                    'label': p['label'],
                    'cls_id': p['cls_id'],
                    'x1': p['coords'][0], 'y1': p['coords'][1],
                    'x2': p['coords'][2], 'y2': p['coords'][3],
                    'count': 1
                }

    if current_region:
        learned_regions.append(current_region)

    is_calibrated = True
    print(f"\n✅ [CALIBRATION COMPLETE] System successfully learned {len(learned_regions)} unique product zones!")
    for i, r in enumerate(learned_regions):
        print(f"   👉 Zone {i+1}: '{r['label']}' sitting between X:[{r['x1']} to {r['x2']}]")

# Ensure the static folder exists for the front-end to find
OUTPUT_DIR = os.path.join('static', 'detections')
os.makedirs(OUTPUT_DIR, exist_ok=True)
def process_live_frame(frame, model):
    """
    🛰️ RUNS ON FRAME 2 ONWARDS:
    Measures the physical length of gap pixels within each learned region.
    Triggers Low Stock if gaps exceed 25% or 50% of shelf length.
    """
    global learned_regions, is_calibrated

    # Auto-fallback to calibration if it hasn't run yet
    if not is_calibrated:
        calibrate_shelf_regions(frame, model)
        return {"annotated_frame": frame, "is_alert": False, "dashboard_data": []}

    results = model(frame)[0]
    annotated_frame = frame.copy()
    
    current_products = []
    current_voids = [] 
    
    for box in results.boxes:
        coords = box.xyxy[0].cpu().numpy().astype(int)
        cls_id = int(box.cls[0])
        label = model.names[cls_id]
        
        if cls_id in [29, 30, 31]: # YOLO gap classes
            current_voids.append({'coords': coords, 'label': label})
        elif cls_id not in [38, 0, 37]: 
            current_products.append({'coords': coords, 'label': label})

    dashboard_data = []
    is_any_alert = False

    print(f"\n=== 🤖 PIXEL-GAP METRIC SCAN @ {datetime.now().strftime('%H:%M:%S')} ===")

    # Evaluate live frame against baseline learned regions
    for i, region in enumerate(learned_regions):
        rx1, ry1, rx2, ry2 = region['x1'], region['y1'], region['x2'], region['y2']
        region_width = rx2 - rx1 # Total horizontal length of the zone
        expected_item = region['label']

        # 1. Isolate live items inside this specific Region
        items_inside = []
        for p in current_products:
            px_mid = (p['coords'][0] + p['coords'][2]) / 2
            if (rx1 <= px_mid <= rx2):
                items_inside.append(p)

        # 2. Calculate the total pixel length of empty gaps inside this Region
        void_pixels = 0
        for v in current_voids:
            vx1, vy1, vx2, vy2 = v['coords']
            
            # Clip overlap boundaries so we don't accidentally count space outside the region
            clip_x1 = max(rx1, vx1)
            clip_x2 = min(rx2, vx2)
            
            if clip_x2 > clip_x1: 
                void_pixels += (clip_x2 - clip_x1)

        # 3. 📊 Convert gap pixels to a % of total shelf region length
        void_percentage = (void_pixels / region_width) * 100 if region_width > 0 else 0

        # Check for displaced products
        mismatches = [x for x in items_inside if x['label'] != expected_item]

        # 🚨 Dynamic Evaluation Logic
        status = "Normal"
        color = (0, 255, 0) # Green UI

        if len(mismatches) > 0:
            status = "Product Mismatch"
            color = (0, 0, 255) # Red UI
            is_any_alert = True
        elif len(items_inside) == 0:
            status = "Stockout"
            color = (0, 0, 255) # Red UI
            is_any_alert = True
        elif void_percentage >= 50: # 🎯 Half of the shelf length is empty
            status = "Low Stock (50% Length Empty)"
            color = (0, 0, 255) # Red UI
            is_any_alert = True
        elif void_percentage >= 25: # 🎯 Quarter of the shelf length is empty
            status = "Low Stock (25% Length Empty)"
            color = (0, 165, 255) # Orange UI
            is_any_alert = True

        # Draw Zone Boundary Overlay
        cv2.rectangle(annotated_frame, (rx1, ry1), (rx2, ry2), (255, 255, 255), 2)
        cv2.putText(annotated_frame, f"Zone {i+1} ({expected_item}) - Gap: {int(void_percentage)}%", 
                    (rx1, ry1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Highlight items being evaluated
        for item in items_inside:
            cv2.rectangle(annotated_frame, (item['coords'][0], item['coords'][1]), (item['coords'][2], item['coords'][3]), color, 2)

        print(f"📂 [Zone {i+1} - {expected_item}] Void Ratio: {int(void_percentage)}% | Status: {status}")
        try:
            # Slice the image using numpy array slicing [y1:y2, x1:x2]
            cropped_shelf = annotated_frame[ry1:ry2, rx1:rx2]
            
            # Save it as Zone1_latest.jpg or Zone2_latest.jpg
            filename = f"Zone{i+1}_latest.jpg"
            filepath = os.path.join(output_dir, filename)
            
            cv2.imwrite(filepath, cropped_shelf)
        except Exception as e:
            print(f"⚠️ Could not crop visual for Zone {i+1}: {e}")
        dashboard_data.append({
            "zone_id": i + 1,
            "expected_item": expected_item,
            "void_ratio": int(void_percentage),
            "status": status
        })
# --- 📸 SAVE THE DETECTED IMAGE AUTOMATICALLY ---
    output_dir = "static/detections"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir) # Creates the folder if it doesn't exist

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save a generic running snapshot for the live dashboard
    save_path_latest = os.path.join(output_dir, "latest_scan.jpg")
    cv2.imwrite(save_path_latest, annotated_frame)

    # If an alert happens (Low stock/Mismatch), save a permanent copy for the logs!
    if is_any_alert:
        alert_filename = f"alert_zone_{timestamp}.jpg"
        save_path_alert = os.path.join(output_dir, alert_filename)
        cv2.imwrite(save_path_alert, annotated_frame)
        print(f"💾 [ALARM] Saved alert image to {save_path_alert}")
    return {"annotated_frame": annotated_frame, "is_alert": is_any_alert, "dashboard_data": dashboard_data}