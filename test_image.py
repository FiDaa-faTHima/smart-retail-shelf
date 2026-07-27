import requests
from datetime import datetime
import cv2
import numpy as np
from ultralytics import YOLO

# -----------------------------
# Load YOLO Model
# -----------------------------
model = YOLO("models\yolov8n.pt")   # Make sure this file exists

# -----------------------------
# Load Image
# -----------------------------
image = cv2.imread("shelf.jpeg")   # Change if needed

if image is None:
    print("Image not loaded")
    exit()

print("Image loaded successfully")

# -----------------------------
# Run Detection
# -----------------------------
results = model(image)
count = len(results[0].boxes)
boxes = results[0].boxes

if len(boxes) == 0:
    print("Shelf is EMPTY")

    alert_data = {
        "issue": "EMPTY",
        "shelf": "Shelf 1",
        "time": datetime.now().strftime("%I:%M %p")
    }

    try:
        requests.post("http://127.0.0.1:5000/api/add_alert", json=alert_data)
        print("Alert sent to Flask")
    except:
        print("Failed to send alert")

# Check if no objects detected (EMPTY shelf example)
if len(boxes) == 0:
    print("Shelf is EMPTY")

    alert_data = {
        "issue": "EMPTY",
        "shelf": "Shelf 1",
        "status": "Pending",
        "time": datetime.now().strftime("%I:%M %p")
    }

    try:
        requests.post("http://127.0.0.1:5000/api/add_alert", json=alert_data)
        print("Alert sent to Flask")
    except:
        print("Failed to send alert")

# -----------------------------
# Split Shelf (Left & Right)
# -----------------------------
height, width, _ = image.shape
mid_x = width // 2

shelf1_count = 0
shelf2_count = 0

for box in boxes:
    x1, y1, x2, y2 = box.xyxy[0]
    center_x = int((x1 + x2) / 2)

    if center_x < mid_x:
        shelf1_count += 1
    else:
        shelf2_count += 1

# -----------------------------
# Status Logic
# -----------------------------
def get_status(count):
    if count >= 2:
        return "NORMAL", (0, 255, 0)      # Green
    elif count == 1:
        return "LOW STOCK", (0, 255, 255)  # Yellow
    else:
        return "EMPTY", (0, 0, 255)      # Red

shelf1_status, color1 = get_status(shelf1_count)
shelf2_status, color2 = get_status(shelf2_count)

print("Shelf 1 Count:", shelf1_count)
print("Shelf 1 Status:", shelf1_status)

print("Shelf 2 Count:", shelf2_count)
print("Shelf 2 Status:", shelf2_status)

# -----------------------------
# Create Separate Shelf Images
# -----------------------------
# -----------------------------
# Split Horizontally (Top & Bottom)
# -----------------------------
height, width, _ = image.shape
mid_y = height // 2

shelf1_img = image[:mid_y, :].copy()      # Top half
shelf2_img = image[mid_y:, :].copy()      # Bottom half
# -----------------------------
# Draw Status Circle (Inside Image)
# -----------------------------
cv2.circle(shelf1_img, (40, 40), 20, color1, -1)
cv2.circle(shelf2_img, (40, 40), 20, color2, -1)

# -----------------------------
# Create Header Above Image
# -----------------------------
header_height = 60

# Shelf 1 Header
header1 = 255 * np.ones((header_height, shelf1_img.shape[1], 3), dtype=np.uint8)
cv2.putText(header1, "Shelf 1: " + shelf1_status,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0), 2)

final_shelf1 = np.vstack((header1, shelf1_img))

# Shelf 2 Header
header2 = 255 * np.ones((header_height, shelf2_img.shape[1], 3), dtype=np.uint8)
cv2.putText(header2, "Shelf 2: " + shelf2_status,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0), 2)

final_shelf2 = np.vstack((header2, shelf2_img))

# -----------------------------
# Show Windows
# -----------------------------
cv2.imshow("Shelf 1", final_shelf1)
cv2.imshow("Shelf 2", final_shelf2)

cv2.waitKey(0)
cv2.destroyAllWindows()