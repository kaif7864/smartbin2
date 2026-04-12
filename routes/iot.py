from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
import qrcode, uuid, os, cv2
from io import BytesIO
import base64
import numpy as np
import json

# Force Legacy Keras to avoid DepthwiseConv2D errors with old .h5 files
os.environ["TF_USE_LEGACY_KERAS"] = "1"

from ultralytics import YOLO
from tensorflow.keras.models import load_model

router = APIRouter()
os.makedirs("captures", exist_ok=True)

# ── Config ────────────────────────────────────────────
SERVER_IP = "10.206.6.171"
PORT      = 8000
LIVE_URL  = f"http://{SERVER_IP}:{PORT}/live"  # Permanent URL

# ── Models ────────────────────────────────────────────
print("Models load ho rahe hain...")
yolo_model = YOLO("yolov8n.pt")

classifier = load_model("P:\Flutter\smart_bin\services\efficientnetv2b2.keras")

CLASS_NAMES = ["cardboard", "glass", "metal", "paper", "plastic", "trash"]

POINTS_MAP = {
    "cardboard": 10,
    "glass":     15,
    "metal":     20,
    "paper":     8,
    "plastic":   12,
    "trash":     2,
}

# ── State — sirf latest reading store hogi ────────────
latest_reading = {}   # hamesha overwrite hota rahega
all_readings   = []   # history ke liye (optional)

# ── Helpers ───────────────────────────────────────────
# YOLO → waste type direct mapping
YOLO_TO_WASTE = {
    "bottle":     "plastic",
    "cup":        "plastic",
    "bowl":       "plastic",
    "can":        "metal",
    "scissors":   "metal",
    "knife":      "metal",
    "fork":       "metal",
    "spoon":      "metal",
    "book":       "paper",
    "cardboard":  "cardboard",
    "box":        "cardboard",
    "wine glass": "glass",
    "vase":       "glass",
}

def preprocess(img):
    # Aspect ratio preserve — stretch nahi hoga
    h, w   = img.shape[:2]
    size   = 124
    scale  = size / max(h, w)
    nh, nw = int(h * scale), int(w * scale)
    resized = cv2.resize(img, (nw, nh))
    canvas  = np.zeros((size, size, 3), dtype=np.float32)
    y_off   = (size - nh) // 2
    x_off   = (size - nw) // 2
    canvas[y_off:y_off+nh, x_off:x_off+nw] = resized / 255.0
    return np.expand_dims(canvas, axis=0)

def classify_image(img_path):
    frame = cv2.imread(img_path)
    if frame is None:
        return "unknown", 0.0

    H, W      = frame.shape[:2]
    results   = yolo_model(frame)
    best_crop  = None
    best_area  = 0
    yolo_waste = None
    yolo_conf  = 0.0

    for r in results:
        if r.boxes is None or len(r.boxes) == 0:
            continue
        for i, box in enumerate(r.boxes.xyxy):
            conf   = float(r.boxes.conf[i])
            cls_id = int(r.boxes.cls[i])
            label  = yolo_model.names[cls_id].lower()

            print(f"[YOLO] {label} @ {round(conf*100,1)}%")

            if conf < 0.3:
                continue

            x1, y1, x2, y2 = map(int, box)
            pad_x = int((x2-x1) * 0.15)
            pad_y = int((y2-y1) * 0.15)
            x1 = max(0, x1-pad_x); y1 = max(0, y1-pad_y)
            x2 = min(W, x2+pad_x); y2 = min(H, y2+pad_y)

            area = (x2-x1) * (y2-y1)
            if area > best_area:
                best_area  = area
                best_crop  = frame[y1:y2, x1:x2]

                # YOLO ne directly pehchana?
                if label in YOLO_TO_WASTE and conf >= 0.45:
                    yolo_waste = YOLO_TO_WASTE[label]
                    yolo_conf  = conf

    # ── YOLO ne pehchana — seedha return ─────────────
    if yolo_waste:
        print(f"[YOLO Direct] {yolo_waste} @ {round(yolo_conf*100,1)}%")
        if best_crop is not None:
            cv2.imwrite("captures/debug_crop.jpg", best_crop)
        return yolo_waste, yolo_conf

    # ── YOLO ne nahi pehchana — EfficientNet ─────────
    print("[YOLO] Known object nahi mila — EfficientNet use kar raha hun")

    if best_crop is None or best_crop.size == 0:
        # Center 60% crop — background hatao
        cy, cx = H//2, W//2
        ch, cw = int(H*0.6), int(W*0.6)
        best_crop = frame[
            max(0, cy-ch//2):min(H, cy+ch//2),
            max(0, cx-cw//2):min(W, cx+cw//2)
        ]

    cv2.imwrite("captures/debug_crop.jpg", best_crop)

    inp   = preprocess(best_crop)
    preds = classifier.predict(inp, verbose=0)

    all_conf = {CLASS_NAMES[i]: round(float(preds[0][i])*100, 1)
                for i in range(len(CLASS_NAMES))}
    print(f"[EfficientNet] {all_conf}")

    idx = int(np.argmax(preds))
    print(f"[Result] {CLASS_NAMES[idx]} @ {round(float(preds[0][idx])*100,1)}%")

    return CLASS_NAMES[idx], float(preds[0][idx])

def img_to_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def make_qr_b64(data):
    """Data (string ya JSON) ko QR code mein convert karo"""
    qr  = qrcode.make(data)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

# ── Endpoints ─────────────────────────────────────────

@router.post("/api/reading")
async def receive_reading(
    weight: float      = Form(...),
    image:  UploadFile = File(...)
):
    global latest_reading

    reading_id = str(uuid.uuid4())[:8]

    # Image save karo
    img_path = f"captures/{reading_id}.jpg"
    with open(img_path, "wb") as f:
        f.write(await image.read())

    # Classify
    waste_type, confidence = classify_image(img_path)
    points = POINTS_MAP.get(waste_type, 0)

    # Latest update karo
    latest_reading = {
        "id":         reading_id,
        "weight":     weight,
        "image":      img_path,
        "waste_type": waste_type,
        "confidence": round(confidence * 100, 1),
        "points":     points,
        "valid":      confidence > 0.5 and waste_type != "trash",
    }

    all_readings.append(latest_reading.copy())

    # ESP32 ko QR data bhejo
    qr_data = {
        "reading_id": reading_id,
        "waste_type": waste_type,
        "points": points,
        "weight_g": weight,
        "confidence": round(confidence * 100, 1),
        "valid": confidence > 0.5 and waste_type != "trash"
    }
    
    return JSONResponse({
        "reading_id":    reading_id,
        "waste_type":    waste_type,
        "confidence":    round(confidence * 100, 1),
        "points_earned": points,
        "weight_g":      weight,
        "valid":         confidence > 0.5 and waste_type != "trash",
        "qr_data":       qr_data
    })


@router.get("/live", response_class=HTMLResponse)
async def live_page():
    """Permanent page — har nayi reading pe auto-refresh hota hai."""

    if not latest_reading:
        # Abhi koi reading nahi — waiting page
        return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head>
  <title>Smart Bin — Live</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="3">
  <style>
    body {{ font-family: sans-serif; background: #f0f4f0;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; margin: 0; }}
    .card {{ background: white; border-radius: 20px; padding: 40px;
             text-align: center; max-width: 360px;
             box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
    .dot {{ display: inline-block; width: 10px; height: 10px;
            background: #1D9E75; border-radius: 50;
            animation: pulse 1s infinite; margin: 0 3px; }}
    @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.3}} }}
    p {{ color: #888; margin-top: 12px; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>Smart Bin</h2>
    <br>
    <span class="dot"></span>
    <span class="dot" style="animation-delay:.2s"></span>
    <span class="dot" style="animation-delay:.4s"></span>
    <p>Koi item nahi rakha abhi...<br>Page auto-refresh ho raha hai</p>
  </div>
</body>
</html>""")

    d = latest_reading
    valid_color = "#1D9E75" if d["valid"] else "#E24B4A"
    valid_text  = "Valid" if d["valid"] else "Invalid"
    img_b64     = img_to_b64(d["image"])

    # QR mein JSON data encode karo
    qr_data = {
        "id": d["id"],
        "waste_type": d["waste_type"],
        "points": d["points"],
        "weight": d["weight"],
        "confidence": d["confidence"],
        "valid": d["valid"]
    }
    qr_json_str = json.dumps(qr_data)
    qr_b64 = make_qr_b64(qr_json_str)

    return HTMLResponse(f"""<!DOCTYPE html>
<html>
<head>
  <title>Smart Bin — Live</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="5">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: sans-serif; background: #f0f4f0; padding: 20px; }}
    .card {{ background: white; border-radius: 20px; padding: 28px;
             max-width: 420px; margin: auto;
             box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
    h1 {{ font-size: 1.3rem; color: #222; margin-bottom: 18px; }}
    img.captured {{ width: 100%; border-radius: 12px; margin-bottom: 16px; }}
    .row {{ display: flex; justify-content: space-between;
            align-items: center; padding: 10px 0;
            border-bottom: 1px solid #f5f5f5; }}
    .row:last-of-type {{ border-bottom: none; }}
    .lbl {{ color: #888; font-size: 0.85rem; }}
    .val {{ font-weight: 600; color: #222; }}
    .weight {{ font-size: 2rem; font-weight: 700; color: #1D9E75; }}
    .points {{ font-size: 1.8rem; font-weight: 700; color: #EF9F27; }}
    .badge {{ padding: 4px 14px; border-radius: 20px;
              font-size: 0.85rem; font-weight: 600;
              color: white; background: {valid_color}; }}
    .qr-section {{ text-align: center; margin-top: 20px; }}
    .live-dot {{ display: inline-block; width: 8px; height: 8px;
                 background: #1D9E75; border-radius: 50%;
                 animation: pulse 1s infinite; margin-right: 6px; }}
    @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.3}} }}
    .footer {{ text-align: center; color: #bbb;
               font-size: 0.75rem; margin-top: 12px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>
      <span class="live-dot"></span>
      Smart Bin — Live
    </h1>

    <img class="captured" src="data:image/jpeg;base64,{img_b64}" />

    <div class="row">
      <span class="lbl">Weight</span>
      <span class="weight">{d['weight']} g</span>
    </div>
    <div class="row">
      <span class="lbl">Waste type</span>
      <span class="val">{d['waste_type'].upper()}</span>
    </div>
    <div class="row">
      <span class="lbl">Confidence</span>
      <span class="val">{d['confidence']}%</span>
    </div>
    <div class="row">
      <span class="lbl">Status</span>
      <span class="badge">{valid_text}</span>
    </div>
    <div class="row">
      <span class="lbl">Points earned</span>
      <span class="points">+{d['points']} pts</span>
    </div>
    <div class="row">
      <span class="lbl">Reading ID</span>
      <span class="val" style="font-size:0.85rem;color:#aaa">{d['id']}</span>
    </div>

    <div class="qr-section">
      <img src="data:image/png;base64,{qr_b64}" width="170"/>
      <div class="footer">
        Yeh QR scan karo apne app se — JSON data automatically add hoga<br>
        Auto-refresh: 5 sec
      </div>
    </div>
  </div>
</body>
</html>""")


@router.get("/history", response_class=HTMLResponse)
async def history():
    """Saari readings ki list."""
    if not all_readings:
        return HTMLResponse("<h2 style='font-family:sans-serif;padding:20px'>Koi history nahi</h2>")
    total_pts = sum(r["points"] for r in all_readings)
    rows = "".join(
        f"<tr><td>{r['id']}</td><td>{r['waste_type']}</td>"
        f"<td>{r['weight']}g</td><td>{r['confidence']}%</td>"
        f"<td>+{r['points']}</td></tr>"
        for r in reversed(all_readings)
    )
    return HTMLResponse(f"""
    <html><head><style>
      body{{font-family:sans-serif;padding:20px}}
      table{{border-collapse:collapse;width:100%}}
      th,td{{border:1px solid #eee;padding:10px;text-align:left}}
      th{{background:#f5f5f5}}
    </style></head><body>
    <h2>Total Points: {total_pts}</h2><br>
    <table>
    <tr><th>ID</th><th>Type</th><th>Weight</th><th>Conf</th><th>Points</th></tr>
    {rows}
    </table>
    </body></html>""")