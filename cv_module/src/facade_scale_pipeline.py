"""
Architectural Scale Reference Report - CV Pipeline
Member 2: CV / Image Processing
----------------------------------------------------
Stages:
 1. Preprocessing  (denoise, CLAHE contrast, unsharp sharpening, blur-quality score)
 2. Reference-scale detection (HOG pedestrian detector -> pixels-per-metre)
 3. Feature detection (Canny + contour analysis -> window/door rectangles)
 4. Dimensional analysis (convert pixel boxes to metres using scale)
 5. Output generation (annotated overlay, scale bar/grid, structured report, validation charts)
"""

import cv2
import numpy as np
import json
import os
import matplotlib.pyplot as plt

AVG_PERSON_HEIGHT_M = 1.70  # reference object assumption

# ---------------------------------------------------------------------------
# 1. PREPROCESSING
# ---------------------------------------------------------------------------
def preprocess(img):
    """Return denoised+contrast-enhanced image and a blur-quality score."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Blur metric: variance of Laplacian (higher = sharper)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    # Denoise
    den = cv2.bilateralFilter(img, d=9, sigmaColor=50, sigmaSpace=50)

    # CLAHE contrast enhancement on luminance channel
    lab = cv2.cvtColor(den, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge((l, a, b))
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # Unsharp mask (mild sharpening, helps with mild blur)
    gauss = cv2.GaussianBlur(enhanced, (0, 0), 3)
    sharpened = cv2.addWeighted(enhanced, 1.5, gauss, -0.5, 0)

    return sharpened, blur_score


# ---------------------------------------------------------------------------
# 2. REFERENCE-SCALE DETECTION (person as known-height object)
# ---------------------------------------------------------------------------
def detect_reference_person(img):
    """Use HOG+SVM pedestrian detector to find a person and return
    (pixels_per_metre, bbox) or (None, None) if not found."""
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    rects, weights = hog.detectMultiScale(
        gray, winStride=(8, 8), padding=(8, 8), scale=1.05
    )

    if len(rects) == 0:
        return None, None

    # Pick the most confident detection
    best_idx = int(np.argmax(weights))
    x, y, w, h = rects[best_idx]
    px_per_m = h / AVG_PERSON_HEIGHT_M
    return px_per_m, (x, y, w, h)


# ---------------------------------------------------------------------------
# 3. FEATURE DETECTION (windows / doors)
# ---------------------------------------------------------------------------
def detect_openings(img):
    """Detect rectangular facade openings (windows/doors) via Canny edges
    + contour analysis. Returns list of (x, y, w, h)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    # Close gaps in edges so contours form closed loops
    kernel = np.ones((7, 7), np.uint8)
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=3)

    contours, _ = cv2.findContours(
        closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )

    H, W = gray.shape
    img_area = H * W
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < img_area * 0.012 or area > img_area * 0.30:
            continue
        aspect = h / float(w)
        if aspect < 0.5 or aspect > 3.0:
            continue
        # rectangularity check
        rect_fill = cv2.contourArea(c) / float(area)
        if rect_fill < 0.65:
            continue

        # contrast check: a real opening looks different from the flat
        # wall surrounding it (darker/glass/recessed vs painted panel)
        inside = gray[y:y + h, x:x + w]
        m = max(4, int(0.08 * max(w, h)))
        x0, y0 = max(0, x - m), max(0, y - m)
        x1, y1 = min(W, x + w + m), min(H, y + h + m)
        outer = gray[y0:y1, x0:x1].copy().astype(int)
        outer[(y - y0):(y - y0) + h, (x - x0):(x - x0) + w] = -1
        ring_vals = outer[outer != -1]
        if ring_vals.size < 10:
            continue
        inside_mean, inside_std = inside.mean(), inside.std()
        ring_mean = ring_vals.mean()
        contrast = abs(inside_mean - ring_mean)
        if contrast < 10 and inside_std < 12:
            continue  # likely a flat wall panel, not a real opening

        boxes.append((x, y, w, h))

    # Remove near-duplicate boxes (NMS-style overlap filter)
    boxes = _filter_overlaps(boxes)
    return boxes


def _filter_overlaps(boxes, iou_thresh=0.5):
    if not boxes:
        return boxes
    boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)
    keep = []
    for b in boxes:
        bx, by, bw, bh = b
        overlap = False
        for k in keep:
            kx, ky, kw, kh = k
            ix = max(0, min(bx + bw, kx + kw) - max(bx, kx))
            iy = max(0, min(by + bh, ky + kh) - max(by, ky))
            inter = ix * iy
            iou = inter / float(bw * bh + kw * kh - inter + 1e-6)
            if iou > iou_thresh:
                overlap = True
                break
        if not overlap:
            keep.append(b)
    return keep


def detect_window_grid(img):
    """Detect a repetitive window grid using Hough line clustering.
    Returns list of (x, y, w, h) window cell boxes."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 30, 100)
    H, W = gray.shape

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                             minLineLength=int(min(H, W) * 0.05),
                             maxLineGap=15)
    if lines is None:
        return []

    h_ys, v_xs = [], []
    for l in lines[:, 0]:
        x1, y1, x2, y2 = l
        if abs(y1 - y2) < 8 and abs(x1 - x2) > W * 0.04:
            h_ys.append((y1 + y2) / 2)
        elif abs(x1 - x2) < 8 and abs(y1 - y2) > H * 0.03:
            v_xs.append((x1 + x2) / 2)

    def cluster(vals, tol):
        vals = sorted(vals)
        clusters = []
        for v in vals:
            if clusters and v - clusters[-1][-1] < tol:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return [int(np.mean(c)) for c in clusters]

    tol = min(H, W) * 0.015
    xs = cluster(v_xs, tol)
    ys = cluster(h_ys, tol)

    if len(xs) < 2 or len(ys) < 2:
        return []

    boxes = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]
            w, h = x1 - x0, y1 - y0
            if w < 15 or h < 15:
                continue
            cell_area = w * h
            if cell_area < (H * W) * 0.0008 or cell_area > (H * W) * 0.05:
                continue
            aspect = h / float(w)
            if aspect < 0.6 or aspect > 3.5:
                continue

            inside = gray[y0:y1, x0:x1]
            m = 4
            x0b, y0b = max(0, x0 - m), max(0, y0 - m)
            x1b, y1b = min(W, x1 + m), min(H, y1 + m)
            outer = gray[y0b:y1b, x0b:x1b].copy().astype(int)
            outer[(y0 - y0b):(y0 - y0b) + h, (x0 - x0b):(x0 - x0b) + w] = -1
            ring_vals = outer[outer != -1]
            if ring_vals.size < 10:
                continue
            contrast = abs(inside.mean() - ring_vals.mean())
            if contrast < 8:
                continue  # not visually distinct from wall -> not a window

            boxes.append((x0, y0, w, h))

    boxes = _filter_overlaps(boxes, iou_thresh=0.3)
    return boxes


# ---------------------------------------------------------------------------
# 4 & 5. DIMENSIONAL ANALYSIS + OUTPUT GENERATION
# ---------------------------------------------------------------------------
def run_pipeline(image_path, out_dir):
    name = os.path.splitext(os.path.basename(image_path))[0]
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(image_path)

    proc, blur_score = preprocess(img)
    px_per_m, person_box = detect_reference_person(proc)

    # Sanity check: a person bbox should be tall & narrow (aspect h/w ~ 1.5-4.5).
    # HOG sometimes false-positives on windows/doors which are wider -> discard.
    if person_box is not None:
        _, _, pw, ph = person_box
        if not (1.3 < (ph / float(pw)) < 4.5):
            px_per_m, person_box = None, None

    # Fallback calibration if no person detected: assume building width
    # corresponds to a typical 12 m frontage (documented assumption,
    # flagged as low-confidence in the report)
    calibration_method = "person_detection"
    if px_per_m is None:
        px_per_m = img.shape[1] / 12.0
        calibration_method = "fallback_default_frontage"

    door_boxes = detect_openings(proc)
    grid_boxes = detect_window_grid(proc)

    # Remove grid cells that overlap with detected doors (avoid double count)
    def overlaps(b, others, thresh=0.3):
        bx, by, bw, bh = b
        for ox, oy, ow, oh in others:
            ix = max(0, min(bx + bw, ox + ow) - max(bx, ox))
            iy = max(0, min(by + bh, oy + oh) - max(by, oy))
            inter = ix * iy
            if inter / float(bw * bh + 1e-6) > thresh:
                return True
        return False

    grid_boxes = [b for b in grid_boxes if not overlaps(b, door_boxes)]

    # --- Annotated overlay ---
    overlay = img.copy()
    features = []

    for (x, y, w, h) in door_boxes:
        w_m, h_m = w / px_per_m, h / px_per_m
        ftype = "Door" if (y + h) > img.shape[0] * 0.85 and h_m > 1.6 else "Window"
        color = (0, 165, 255) if ftype == "Door" else (0, 255, 0)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, 2)
        cv2.putText(overlay, f"{ftype}: {w_m:.2f}m x {h_m:.2f}m", (x, max(15, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        features.append({"type": ftype, "x": x, "y": y, "width_px": w, "height_px": h,
                          "width_m": round(w_m, 2), "height_m": round(h_m, 2),
                          "area_m2": round(w_m * h_m, 2)})

    for (x, y, w, h) in grid_boxes:
        w_m, h_m = w / px_per_m, h / px_per_m
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(overlay, f"Window: {w_m:.2f}m x {h_m:.2f}m", (x, max(15, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)
        features.append({"type": "Window", "x": x, "y": y, "width_px": w, "height_px": h,
                          "width_m": round(w_m, 2), "height_m": round(h_m, 2),
                          "area_m2": round(w_m * h_m, 2)})

    if person_box is not None:
        x, y, w, h = person_box
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (255, 0, 0), 2)
        cv2.putText(overlay, f"Ref: {AVG_PERSON_HEIGHT_M}m person",
                     (x, max(15, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                     (255, 0, 0), 1, cv2.LINE_AA)

    # --- Scale bar (1 metre grid) ---
    grid = overlay.copy()
    step = int(round(px_per_m))
    if step > 4:
        for gx in range(0, grid.shape[1], step):
            cv2.line(grid, (gx, 0), (gx, grid.shape[0]), (200, 200, 0), 1)
        for gy in range(0, grid.shape[0], step):
            cv2.line(grid, (0, gy), (grid.shape[1], gy), (200, 200, 0), 1)
    # Scale bar legend (bottom-left): 1m and 5m bars
    bar_y = grid.shape[0] - 25
    cv2.line(grid, (15, bar_y), (15 + int(px_per_m), bar_y), (0, 0, 255), 4)
    cv2.putText(grid, "1 m", (15, bar_y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.line(grid, (15, bar_y + 12), (15 + int(px_per_m * 5), bar_y + 12), (0, 0, 255), 4)
    cv2.putText(grid, "5 m", (15, bar_y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    overlay_path = os.path.join(out_dir, f"{name}_annotated.jpg")
    grid_path = os.path.join(out_dir, f"{name}_scalegrid.jpg")
    cv2.imwrite(overlay_path, overlay)
    cv2.imwrite(grid_path, grid)

    # --- Validation chart ---
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].imshow(cv2.cvtColor(cv2.Canny(cv2.cvtColor(proc, cv2.COLOR_BGR2GRAY), 50, 150), cv2.COLOR_GRAY2RGB))
    axes[0].set_title("Canny Edge Map (feature detection input)")
    axes[0].axis("off")

    types = [f["type"] for f in features]
    areas = [f["area_m2"] for f in features]
    axes[1].bar(range(len(features)), areas,
                 color=["tab:orange" if t == "Door" else "tab:blue" for t in types])
    axes[1].set_xticks(range(len(features)))
    axes[1].set_xticklabels([f"{f['type']}\n{i+1}" for i, f in enumerate(features)], fontsize=8)
    axes[1].set_ylabel("Area (m^2)")
    axes[1].set_title(f"Detected Opening Areas\nBlur score={blur_score:.1f}, scale={calibration_method}")
    plt.tight_layout()
    chart_path = os.path.join(out_dir, f"{name}_validation_chart.png")
    plt.savefig(chart_path, dpi=130)
    plt.close(fig)

    # --- Structured report ---
    report = {
        "image": os.path.basename(image_path),
        "image_quality": {
            "blur_variance_laplacian": round(blur_score, 2),
            "quality_flag": "low (blurred)" if blur_score < 100 else "ok"
        },
        "calibration": {
            "method": calibration_method,
            "pixels_per_metre": round(px_per_m, 2),
            "reference_height_assumed_m": AVG_PERSON_HEIGHT_M if calibration_method == "person_detection" else None
        },
        "detected_features": features
    }
    report_path = os.path.join(out_dir, f"{name}_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    return report, overlay_path, grid_path, chart_path, report_path


if __name__ == "__main__":
    import sys
    out_dir = "/home/claude/results"
    os.makedirs(out_dir, exist_ok=True)
    for p in sys.argv[1:]:
        r, *_ = run_pipeline(p, out_dir)
        print(json.dumps(r, indent=2))
