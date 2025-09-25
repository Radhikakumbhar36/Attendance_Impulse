#!/usr/bin/env python3
"""
Enhanced GPS Extractor with EXIF injection
- Extracts GPS coordinates from EXIF or OCR overlay
- If GPS missing in EXIF, injects detected GPS back into EXIF
"""

import re
import os
import cv2
import pytesseract
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from datetime import datetime
import piexif

# ---------------- Tesseract configuration ----------------
def _configure_tesseract_path():
    """Configure pytesseract.tesseract_cmd robustly on Windows."""
    try:
        env_path = os.environ.get('TESSERACT_CMD') or os.environ.get('TESSERACT_EXE')
        if env_path and os.path.isfile(env_path):
            pytesseract.pytesseract.tesseract_cmd = env_path
            print(f"🔧 Using Tesseract from env: {env_path}")
            return
        common = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        if os.path.isfile(common):
            pytesseract.pytesseract.tesseract_cmd = common
            print(f"🔧 Using Tesseract from common path: {common}")
            return
        common86 = r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe"
        if os.path.isfile(common86):
            pytesseract.pytesseract.tesseract_cmd = common86
            print(f"🔧 Using Tesseract from common path: {common86}")
            return
        print("⚠️ Tesseract path not found; relying on system PATH")
    except Exception as e:
        print(f"⚠️ Tesseract path configuration error: {e}")

_configure_tesseract_path()

# ---------------- OCR helpers ----------------
def clean_ocr_text(text):
    """Clean OCR text to fix common recognition errors"""
    if not text:
        return ""
    replacements = {'O':'0','I':'1','l':'1','S':'5','B':'8','G':'6','Z':'2','T':'7'}
    for old,new in replacements.items():
        text = text.replace(old,new)
    # Remove extra whitespace and newlines
    text = re.sub(r'\s+', ' ', text.strip())
    return text

def extract_gps_from_text_overlay(photo_path):
    """Extract GPS from visual text overlay using OCR"""
    try:
        image = cv2.imread(photo_path)
        if image is None:
            print("❌ Could not read image file")
            return None, None
        height, width = image.shape[:2]
        crop_start = int(height * 0.5)
        cropped_image = image[crop_start:, :]

        # Preprocess: grayscale, threshold for better OCR
        def preprocess(img):
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
            _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return th

        pil_cropped = Image.fromarray(cv2.cvtColor(cropped_image, cv2.COLOR_BGR2RGB))
        pil_full = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        pil_cropped_th = Image.fromarray(preprocess(cropped_image))
        pil_full_th = Image.fromarray(preprocess(image))

        ocr_results = {}
        for label, pil_img in {
            'cropped': pil_cropped,
            'full': pil_full,
            'cropped_th': pil_cropped_th,
            'full_th': pil_full_th
        }.items():
            text = pytesseract.image_to_string(pil_img, config='--psm 6')
            ocr_results[label] = clean_ocr_text(text)
            # Save OCR output for debugging
            try:
                debug_dir = os.path.join(os.path.dirname(photo_path), "ocr_debug")
                os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, f"{os.path.basename(photo_path)}_{label}.txt"), "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception as e:
                print(f"⚠️ Could not save OCR debug output: {e}")

        # Print all OCR results for troubleshooting
        for label, text in ocr_results.items():
            print(f"📝 OCR ({label}): {text[:100]}...")

        # Patterns for extraction
        gps_patterns = [
            r'(-?\d{1,3}\.\d+)\s*[°, ]+\s*(-?\d{1,3}\.\d+)',  # decimal
            r'Lat\s*[:=]?\s*(-?\d{1,3}\.\d+)\s*°?\s*[,;]?\s*Long\s*[:=]?\s*(-?\d{1,3}\.\d+)\s*°?',
            r'Latitude\s*[:=]?\s*(-?\d{1,3}\.\d+)\s*°?\s*[,;]?\s*Longitude\s*[:=]?\s*(-?\d{1,3}\.\d+)\s*°?',
            r'(\d{1,3})[°: ]+(\d{1,2})[\'′: ]+(\d{1,2}(?:\.\d+)?)[\"″: ]+[NSns]?[, ]+(\d{1,3})[°: ]+(\d{1,2})[\'′: ]+(\d{1,2}(?:\.\d+)?)[\"″: ]+[EWew]?',  # DMS
        ]
        date_patterns = [
            r'(\d{1,2})[\-/](\d{1,2})[\-/](\d{2,4})',  # 22/09/2025 or 09/22/2025
            r'(\d{4})[\-/](\d{1,2})[\-/](\d{1,2})',    # 2025-09-22
        ]
        time_patterns = [
            r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM|am|pm)?',
        ]
        address_pattern = r'([A-Za-z0-9,\- ]+Maharashtra|India|Pune|Chinchwad|Pimpri|\d{6})'  # crude, adjust as needed

        found = {"lat": None, "lon": None, "date": None, "time": None, "address": None}
        for label, text in ocr_results.items():
            # GPS
            for pattern in gps_patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        if len(match.groups()) == 2:
                            lat = float(match.group(1))
                            lon = float(match.group(2))
                        elif len(match.groups()) == 6:
                            d1, m1, s1, d2, m2, s2 = match.groups()
                            lat = int(d1) + int(m1)/60 + float(s1)/3600
                            lon = int(d2) + int(m2)/60 + float(s2)/3600
                        else:
                            continue
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            found["lat"] = lat
                            found["lon"] = lon
                            print(f"✅ GPS found in OCR ({label}): {lat},{lon}")
                            break
                    except Exception as e:
                        print(f"⚠️ Regex parse error: {e}")
                        continue
            # Date
            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        if len(match.groups()) == 3:
                            g1, g2, g3 = match.groups()
                            if len(g3) == 4:
                                # Ambiguous dd/mm/yyyy vs mm/dd/yyyy; disambiguate by value ranges
                                a = int(g1)
                                b = int(g2)
                                y = int(g3)
                                if a > 12 and 1 <= b <= 12:
                                    d, m = a, b  # clearly dd/mm
                                elif b > 12 and 1 <= a <= 12:
                                    d, m = b, a  # mm/dd -> convert to dd/mm
                                else:
                                    # Both <= 12; keep as-is (assume dd/mm)
                                    d, m = a, b
                            else:
                                # yyyy-mm-dd
                                y, m, d = int(g1), int(g2), int(g3)
                            found["date"] = f"{int(d):02d}/{int(m):02d}/{int(y):04d}"
                            print(f"✅ Date found in OCR ({label}): {found['date']}")
                            break
                    except Exception as e:
                        print(f"⚠️ Date parse error: {e}")
                        continue
            # Time
            for pattern in time_patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        h, mi = match.group(1), match.group(2)
                        s = match.group(3) if match.group(3) else "00"
                        ampm = match.group(4) if match.group(4) else ""
                        found["time"] = f"{h}:{mi}:{s} {ampm}".strip()
                        print(f"✅ Time found in OCR ({label}): {found['time']}")
                        break
                    except Exception as e:
                        print(f"⚠️ Time parse error: {e}")
                        continue
            # Address (crude)
            match = re.search(address_pattern, text)
            if match:
                found["address"] = match.group(0)
                print(f"✅ Address found in OCR ({label}): {found['address']}")

        if found["lat"] is not None and found["lon"] is not None:
            return found["lat"], found["lon"], found["date"], found["time"], found["address"]
        print("❌ No valid GPS found in OCR (all attempts)")
        return None, None, found["date"], found["time"], found["address"]
    except Exception as e:
        print(f"❌ OCR GPS error: {e}")
        return None, None

# ---------------- EXIF helpers ----------------
def _deg_to_dms_rational(deg_float):
    """Convert decimal degrees to EXIF rational DMS format"""
    deg_abs = abs(deg_float)
    d = int(deg_abs)
    m = int((deg_abs - d)*60)
    s = round((deg_abs - d - m/60)*3600 * 100)
    return [(d,1),(m,1),(s,100)]

def inject_gps_into_exif(photo_path, lat, lon):
    """Inject GPS into EXIF using piexif"""
    try:
        exif_dict = {"0th":{}, "Exif":{}, "GPS":{}, "1st":{}, "thumbnail":None}
        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: b'N' if lat>=0 else b'S',
            piexif.GPSIFD.GPSLatitude: _deg_to_dms_rational(lat),
            piexif.GPSIFD.GPSLongitudeRef: b'E' if lon>=0 else b'W',
            piexif.GPSIFD.GPSLongitude: _deg_to_dms_rational(lon),
        }
        exif_dict["GPS"] = gps_ifd
        exif_bytes = piexif.dump(exif_dict)
        img = Image.open(photo_path)
        img.save(photo_path, exif=exif_bytes)
        print(f"✅ Injected GPS into EXIF: {lat},{lon}")
    except Exception as e:
        print(f"⚠️ Failed to inject GPS: {e}")

def extract_gps_from_exif(photo_path):
    """Extract GPS from EXIF"""
    try:
        img = Image.open(photo_path)
        exif_data = img.info.get("exif")
        if not exif_data:
            return None,None
        exif_dict = piexif.load(exif_data)
        gps = exif_dict.get("GPS")
        if not gps or piexif.GPSIFD.GPSLatitude not in gps:
            return None,None
        def rational_to_float(rat):
            return float(rat[0][0])/float(rat[0][1]) + float(rat[1][0])/float(rat[1][1])/60 + float(rat[2][0])/float(rat[2][1])/3600
        lat = rational_to_float(gps[piexif.GPSIFD.GPSLatitude])
        lon = rational_to_float(gps[piexif.GPSIFD.GPSLongitude])
        if gps[piexif.GPSIFD.GPSLatitudeRef]==b'S':
            lat = -lat
        if gps[piexif.GPSIFD.GPSLongitudeRef]==b'W':
            lon = -lon
        return lat, lon
    except Exception:
        return None,None

# ---------------- Datetime extraction ----------------
def extract_datetime_from_exif(photo_path):
    try:
        img = Image.open(photo_path)
        exif_data = img._getexif() or {}
        for tag_id,value in exif_data.items():
            tag = TAGS.get(tag_id,tag_id)
            if tag in ["DateTimeOriginal","DateTime"]:
                parts = str(value).split()
                y,m,d = parts[0].split(':')
                hh,mm,ss = parts[1].split(':') if len(parts)>1 else ('0','0','0')
                return datetime(int(y),int(m),int(d),int(hh),int(mm),int(ss))
        return None
    except:
        return None

# ---------------- Main extraction ----------------
def extract_gps_and_datetime(photo_path):
    print(f"🔍 Extracting from {photo_path}")
    lat, lon = extract_gps_from_exif(photo_path)
    if lat is not None and lon is not None:
        dt = extract_datetime_from_exif(photo_path)
        return lat, lon, dt, "", "EXIF"

    # EXIF missing → try OCR
    lat, lon, date_str, time_str, address = extract_gps_from_text_overlay(photo_path)
    if lat is not None and lon is not None:
        # Build datetime from extracted date/time
        dt, ok = extract_datetime_from_text_overlay(photo_path)
        if not ok or dt is None:
            print("❌ Could not construct datetime from OCR overlay")
            return None, None, None, address, "TIME_PARSE_FAILED"
        # Validate date with today (accept dd/mm or mm/dd already handled in extractor)
        today = datetime.now().date()
        if dt.date() == today:
            print(f"✅ Date matches today: {dt.strftime('%d/%m/%Y')}")
            # Inject GPS into EXIF for future fast reads
            inject_gps_into_exif(photo_path, lat, lon)
            return lat, lon, dt, address, "OCR+Injected"
        else:
            print(f"❌ Date in photo ({dt.strftime('%d/%m/%Y')}) does not match today ({today.strftime('%d/%m/%Y')})")
            return None, None, None, address, "DATE_MISMATCH"

    return None, None, None, None, None

# ---------------- Test ----------------
def test(photo_path):
    lat, lon, dt, address, method = extract_gps_and_datetime(photo_path)
    if lat and lon:
        print(f"✅ GPS: {lat},{lon} | Datetime: {dt} | Address: {address} | Method: {method}")
    elif method == "DATE_MISMATCH":
        print("❌ Date in photo does not match today's date. Attendance not marked.")
    else:
        print("❌ No GPS found")

if __name__=="__main__":
    import sys
    if len(sys.argv)!=2:
        print("Usage: python gps_extractor.py <photo_path>")
        exit(1)
    test(sys.argv[1])

def extract_datetime_from_text_overlay(photo_path):
    """Extract datetime from text overlay using OCR. Returns (datetime, ok)."""
    try:
        # Reuse OCR to get date and time strings
        _, _, date_str, time_str, _ = extract_gps_from_text_overlay(photo_path)
        if not date_str or not time_str:
            return None, False
        # Normalize time (handle optional seconds and AM/PM)
        time_str = time_str.upper().replace("  ", " ").strip()
        # Build datetime in common formats
        for fmt in [
            "%d/%m/%Y %I:%M:%S %p",
            "%d/%m/%Y %I:%M %p",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
        ]:
            try:
                dt = datetime.strptime(f"{date_str} {time_str}", fmt)
                return dt, True
            except Exception:
                continue
        return None, False
    except Exception:
        return None, False

def validate_photo_time(photo_datetime, upload_time=None, max_minutes_diff=10):
    """Validate photo time is within max_minutes_diff of upload time"""
    if not photo_datetime:
        return False, "No time extracted from photo"
    
    # Use upload time if provided, otherwise use current system time
    reference_time = upload_time if upload_time else datetime.now()
    time_diff = abs((photo_datetime - reference_time).total_seconds() / 60)  # minutes
    
    if time_diff <= max_minutes_diff:
        return True, f"Photo time valid (diff from upload: {time_diff:.1f} min)"
    else:
        return False, f"Photo time differs from upload time by {time_diff:.1f} minutes (max allowed: {max_minutes_diff} min)"