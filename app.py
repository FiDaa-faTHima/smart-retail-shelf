from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, flash, session
import cv2
import os
import numpy as np
from datetime import datetime
from ultralytics import YOLO
from werkzeug.security import generate_password_hash, check_password_hash
from database_manager import get_db_connection
from detection_engine import process_live_frame
from database_manager import log_smart_shelf_scans
import detection_engine
import json
import time
import threading
import sqlite3 # <--- ADD THIS LINE
users_db = {}
# from database_manager import insert_detection

# --- 1. Define these at the TOP of your script (outside any function) ---
latest_data = {} # Global variable to store current detection result
global shelf_data, camera_active, terms_accepted, urgent_shelves, detection_interval

# import logging
# log = logging.getLogger('werkzeug')
# log.setLevel(logging.ERROR)
app = Flask(__name__)
app.secret_key = "smart_retail_secret_key" # Required for popups (flashing)
# This is the "Professional" way (works on Windows, Mac, and Linux)

model = YOLO("models/best.pt")

# This prints the dictionary of names stored inside the file
# print(model.names)
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
# Load Model
model.to('cpu')
# Shelf Data
global_stats = {
    'racks': {},
    'is_alert': False
}
last_detection_time = 0
camera_active = False  # Start OFF
camera = None          # No hardware connection yet
terms_accepted = False
detection_interval = 5
shelf_data = {"top_count": 0, "bottom_count": 0}
urgent_shelves = []
# racks_to_process = data.get('racks', {})
#  Make sure this file exists

# Shared frames for the video feed
# --- Add this to your Global Variables at the top ---
auto_monitoring_active = False  # Controlled by your UI switch
shelf_layout_memory = {}               # To store "Normal" crowded states
output_frame = None
raw_frame = None     # The Clean Camera Frame (for Alerts Page)
lock = threading.Lock() # Prevents errors when two tasks touch the same image
# This is your "Background Worker"
# 1. Keep the function (it's very good for stability)
# frame = cv2.resize(frame,(640,480))
def open_camera():
    """Cycles through ports [1, 2, 0] to find an available camera."""
    ports = [1, 2, 0] 
    for index in ports:
        print(f"🔍 Testing Camera Port {index}...")
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            ret, _ = cap.read() # Read a test frame to verify it's active
            if ret:
                print(f"✅ Success! Connected to Camera Port {index}")
                return cap
        cap.release()
    return None


@app.route('/video_feed')
def video_feed():
    """This is the URL the <img> tag will call to stream the live feed."""
    # Safety: If terms aren't accepted or camera isn't active, it won't stream
    if not terms_accepted or not camera_active:
        return "Camera Access Required", 403

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
# 2. CHANGE THIS: Initialize as None


# 3. Your detection_thread already handles the rest:
# if camera is None:
#     camera = open_camera()
import time
from datetime import datetime

# --- Global Tracking Variables ---
auto_monitoring_active = False
detection_interval = 5  # Default to 5 seconds
last_detection_time = 0



import time
from datetime import datetime

# --- 🚀 Global State Variables (Top of app.py) ---
auto_monitoring_active = False # Default OFF
detection_interval = 5        # Default 5 seconds
last_detection_time = 0
latest_dashboard_data = []
def detection_thread():
    global raw_frame, camera, camera_active, terms_accepted, auto_monitoring_active, last_detection_time, detection_interval,latest_dashboard_data 
    
    while True:
        if not terms_accepted or not camera_active:
            if camera is not None:
                camera.release()
                camera = None
            time.sleep(0.5)
            continue

        if camera is None:
            camera = open_camera()
            if camera is None:
                time.sleep(2)
                continue

        success, frame = camera.read()
        if not success:
            time.sleep(0.1)
            continue

        with lock:
            raw_frame = frame.copy()

        current_time = time.time()

        # 🎯 3. YOLO TRIGGER PULSE (Runs when switch is ON)
        if auto_monitoring_active and (current_time - last_detection_time >= detection_interval):
            print(f"\n--- 🤖 YOLO LIVE SCAN (Interval: {detection_interval}s) @ {datetime.now().strftime('%H:%M:%S')} ---")
            
            # ✅ CALL THE DYNAMIC PIXEL-GAP ENGINE HERE
            detection_output = process_live_frame(frame, model)
            # Inside detection_thread, right under detection_output = process_live_frame(...)
            global latest_dashboard_data
            latest_dashboard_data = detection_output.get("dashboard_data", [])
                        # Grab the parsed visual readings
            dashboard_data = detection_output.get("dashboard_data", [])
            is_alert = detection_output.get("is_alert", False)

            if not dashboard_data:
                print("❌ Scan Complete: Evaluating baseline regions...")
            else:
                print(f"✅ Scan Complete: Evaluated {len(dashboard_data)} shelf zones.")
                if is_alert:
                    print("🚨 [ALERT] Displaced items or Low stock detected!")
          
            # ✅ We pass the 'frame' so OpenCV can crop it and save it!
            log_smart_shelf_scans(latest_dashboard_data, detection_engine.learned_regions, frame)
            last_detection_time = current_time

        time.sleep(0.03) # Standard 30fps throttle # Standard 30fps throttle
                
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/api/toggle_monitoring', methods=['POST'])
def toggle_monitoring():
    global auto_monitoring_active
    data = request.get_json()
    
    # Read what the user clicked
    auto_monitoring_active = data.get('active', False)
    
    status_msg = "STARTED" if auto_monitoring_active else "STOPPED"
    print(f"\n[SYSTEM] 🔔 Auto Monitoring {status_msg}")
    
    # Send the real state BACK to the browser so JS can update the UI
    return jsonify({"status": "success", "active": auto_monitoring_active})


def generate_frames():
    global output_frame, lock

    while True:

        with lock:
            if raw_frame is None:
                frame = np.zeros((480,640,3), dtype=np.uint8)
                cv2.putText(frame,"Waiting for camera...",
                            (150,240),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,(255,255,255),2)
            else:
                frame = raw_frame.copy()

        if not terms_accepted or not camera_active:
            frame = np.zeros((480,640,3), dtype=np.uint8)
            msg = "ACCEPT TERMS FIRST" if not terms_accepted else "CAMERA OFF"
            cv2.putText(frame,msg,(120,240),
                        cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,0,255),2)

        ret, buffer = cv2.imencode('.jpg', frame)

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' +
               buffer.tobytes() +
               b'\r\n')



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('fullname')
        user_name = request.form.get('username')
        pwd = request.form.get('password')
        
        hashed_password = generate_password_hash(pwd, method='pbkdf2:sha256')

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (fullname, username, password) VALUES (?, ?, ?)",
                         (full_name, user_name, hashed_password))
            conn.commit()
            flash("Registration Successful! Please Login.")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists!")
        finally:
            conn.close()
            
    return render_template('register.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        typed_user = request.form.get('username')
        typed_pass = request.form.get('password')

        conn = get_db_connection()
        # Fetch the user from SQLite
        user_row = conn.execute("SELECT * FROM users WHERE username = ?", (typed_user,)).fetchone()
        conn.close()

        if user_row and check_password_hash(user_row['password'], typed_pass):
            session['user'] = user_row['username']
            session['fullname'] = user_row['fullname']
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password.")
            
    return render_template('login.html')

    # This now matches the 'user' key we set in login
@app.route('/dashboard')
def dashboard():
    # Fetch the name from the session pocket
    user_name = session.get('fullname', 'Guest') 
    
    # Send it to the HTML as the variable "name"
    return render_template('dashboard.html', name=user_name)

@app.route('/api/stats')
def get_stats():
    # Convert entire dict to string and back to clean out NumPy types
    clean_stats = json.loads(json.dumps(global_stats, default=str))
    return jsonify(clean_stats)
    
    # This renders shelf_details.html and passes the shelf number to the UI
@app.route('/logout')
def logout():
    session.pop('user', None) # Remove user from session
    return redirect(url_for('login'))
@app.route('/api/toggle_camera', methods=['POST'])
def toggle_camera():
    global camera_active, camera
    
    # 🔄 Flip the state
    camera_active = not camera_active
    
    if not camera_active:
        # 🔌 Cut physical power to the USB/Laptop webcam
        if camera is not None:
            camera.release()
            camera = None
        print("\n[SYSTEM] 🛑 Camera Hardware Released (OFF)")
    else:
        print("\n[SYSTEM] 🟢 Camera Hardware Armed (ON)")

    return jsonify({"success": True, "status": "ON" if camera_active else "OFF"})
@app.route('/api/accept_terms', methods=['POST'])
def accept_terms():
    global terms_accepted, camera_active
    terms_accepted = True
    camera_active = True  # Instantly wakes up the USB hardware
    return jsonify({"success": True})
@app.route('/api/grant_system_permission', methods=['POST'])
def grant_system_permission():
    global terms_accepted
    terms_accepted= True
    print(">>> SECURITY ALERT: System Terms Accepted. Camera is now UNLOCKED.") # This will show in VS Code
    return jsonify({"success": True})

@app.route('/api/set_interval', methods=['POST'])
def set_interval():
    global detection_interval
    data = request.get_json()
    
    # Cast the incoming string to a clean integer (e.g., 5, 10, 30)
    seconds = int(data.get('seconds', 5))
    detection_interval = seconds
    
    print(f"\n[SYSTEM] ⏱️ Refresh Rate updated to {detection_interval} seconds.")
    return jsonify({"success": True, "interval": detection_interval})
@app.route('/api/update_profile', methods=['POST'])
def update_profile():
    import sqlite3
    data = request.get_json()
    
    email = data.get('email')
    password = data.get('password')

    if not email:
        return jsonify({"success": False, "message": "Email is required"}), 400

    conn = sqlite3.connect("retail.db")
    cursor = conn.cursor()

    try:
        if password:
            # Updating both Email and Password
            cursor.execute('''
                UPDATE users 
                SET email = ?, password = ? 
                WHERE role = 'admin'
            ''', (email, password))
        else:
            # Updating Email only
            cursor.execute('''
                UPDATE users 
                SET email = ? 
                WHERE role = 'admin'
            ''', (email,))

        conn.commit()
        success = True
        message = "Profile successfully updated!"
    except Exception as e:
        conn.rollback()
        success = False
        message = str(e)
    finally:
        conn.close()

    return jsonify({"success": success, "message": message})
@app.route('/get_alerts_log')
def get_alerts_log():
    conn = sqlite3.connect('retail.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Get the 10 most recent alerts
    alerts = cursor.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 10").fetchall()
    conn.close()
    
    # Convert to a list of dictionaries so JavaScript can read it
    return jsonify([dict(row) for row in alerts])      
@app.route('/api/real_inventory')
def real_inventory():
    conn = get_db_connection()
    # Pull the latest counts for each product from notifications
    rows = conn.execute('''
        SELECT zone_id, count, status, detected_at 
        FROM shelf_notifications 
        ORDER BY detected_at DESC LIMIT 5
    ''').fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in rows])  
@app.route('/details/<shelf_id>')
def shelf_details(shelf_id):
    # Render the shelf details page and pass the ID to it
    return render_template('shelf_details.html', shelf_id=shelf_id)  
@app.route('/api/get_latest_alerts')
def get_latest_alerts():
    # We grab the global dashboard data from your thread
    global latest_dashboard_data 
    
    if not latest_dashboard_data:
        return jsonify([]) # Return empty list if YOLO hasn't run yet

    return jsonify(latest_dashboard_data)   
@app.route('/api/get_detection_logs')
def get_detection_logs():
    import sqlite3
    
    # Check if DB exists, if not return empty list
    if not os.path.exists("retail.db"):
        return jsonify([])

    conn = sqlite3.connect("retail.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    logs = []

    try:
        # 1. Fetch from Alerts Table
        cursor.execute('''
            SELECT 'Alert' as type, id, camera_id, region_id as shelf, product_name, alert_type as status, timestamp 
            FROM shelf_alerts 
            ORDER BY timestamp DESC LIMIT 50
        ''')
        for row in cursor.fetchall():
            logs.append(dict(row))

        # 2. Fetch from Normal Logs Table
        cursor.execute('''
            SELECT 'Normal' as type, id, camera_id, shelf_id as shelf, product_name, status, timestamp 
            FROM shelf_normal_logs 
            ORDER BY timestamp DESC LIMIT 50
        ''')
        for row in cursor.fetchall():
            logs.append(dict(row))

        # Sort combined logs by timestamp (Newest First)
        logs.sort(key=lambda x: x['timestamp'], reverse=True)

    except Exception as e:
        print(f"❌ Error reading logs from DB: {e}")

    conn.close()
    return jsonify(logs[:50]) 
@app.route('/api/get_shelf_details/<int:zone_id>')
def get_shelf_details(zone_id):
    import sqlite3
    import json

    conn = sqlite3.connect("retail.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    shelf_data = {}

    try:
        # 1. Get calibration map data (Location + Product Names)
        cursor.execute("SELECT * FROM shelf_map WHERE id = ?", (zone_id,))
        map_row = cursor.fetchone()

        # 2. Get latest live telemetry from normal logs or alerts
        cursor.execute('''
            SELECT status, timestamp, snapshot_path, product_count 
            FROM (
                SELECT status, timestamp, snapshot_path, product_count FROM shelf_normal_logs WHERE shelf_id = ?
                UNION ALL
                SELECT alert_type as status, timestamp, snapshot_path, product_count FROM shelf_alerts WHERE region_id = ?
            ) ORDER BY timestamp DESC LIMIT 1
        ''', (f"Zone {zone_id}", f"Zone {zone_id}"))
        live_row = cursor.fetchone()

        # 🧩 Package response
        if map_row:
            shelf_data = {
                "id": zone_id,
                "name": map_row["zone_name"],
                "product_cls": map_row["product_id"],
                "coords": [map_row["x1"], map_row["y1"], map_row["x2"], map_row["y2"]],
                "max_capacity": map_row["max_capacity"],
                "status": live_row["status"] if live_row else "Normal",
                "last_time": live_row["timestamp"] if live_row else "No readings yet",
                "img_path": live_row["snapshot_path"] if live_row else f"static/detections/Zone{zone_id}_latest.jpg",
                "count": live_row["product_count"] if live_row else 0
            }
        else:
            # Fallback for visual mock testing if table isn't calibrated
            shelf_data = {
                "id": zone_id,
                "name": f"Dynamic Shelf {zone_id}",
                "product_cls": "Generic",
                "coords": [0,0,0,0],
                "max_capacity": 10,
                "status": "Unknown",
                "last_time": "N/A",
                "img_path": f"static/detections/Zone{zone_id}_latest.jpg",
                "count": 0
            }

    except Exception as e:
        print(f"❌ DB Fetch Error for Shelf Details: {e}")

    conn.close()
    return jsonify(shelf_data)    
@app.route('/api/resolve_alert/<int:alert_id>', methods=['DELETE'])
def resolve_alert(alert_id):
    import sqlite3
    
    conn = sqlite3.connect("retail.db")
    cursor = conn.cursor()

    try:
        # Delete the specific alert from your detection log table
        cursor.execute("DELETE FROM shelf_alerts WHERE id = ?", (alert_id,))
        conn.commit()
        success = True
        message = "Alert successfully resolved and deleted."
    except Exception as e:
        conn.rollback()
        success = False
        message = str(e)
    finally:
        conn.close()

    return jsonify({"success": success, "message": message})    
    # Return the top 50 combined logs 
if __name__ == '__main__':
    # 1. Start the background worker
    # 'daemon=True' means it will close automatically when you stop the app
    
    t=threading.Thread(target=detection_thread, daemon=True)
    t.start()
    # import logging
    # logging.getLogger('werkzeug').setLevel(logging.WARNING)
    # 2. Start the Flask Website
    app.run(host='localhost', port=5000, debug=True, use_reloader=False)