# Architectural Scale Reference — CV / Image Processing Module
**Member 2: CV / Image Processing Lead**

This module is the CV component of the "Architectural Scale Reference Report" project.
It converts a facade photograph into real-world dimensional data for windows, doors, and
other features, with annotated visual outputs.

## Contents

```
cv_module/
├── src/
│   └── facade_scale_pipeline.py     # Automatic CV pipeline (preprocessing,
│                                     # calibration, detection, analysis, output)
├── tool/
│   └── scale_reference_tool.html    # Interactive browser tool: manual calibration
│                                     # + feature marking + export (PNG/JSON)
├── results/                          # Sample outputs across 8 test images
│   ├── *_annotated.jpg               # Detected features with dimension labels
│   ├── *_scalegrid.jpg               # 1m grid + scale bar overlay
│   ├── *_validation_chart.png        # Edge map + detected-area chart
│   └── *_report.json                 # Structured dimensional data
└── docs/
    └── CV_Pipeline_Methodology_Report.md   # Full methodology, results, limitations
```

## 1. Automatic pipeline (`src/facade_scale_pipeline.py`)

Five-stage OpenCV pipeline:

1. **Preprocessing** — bilateral denoise, CLAHE contrast enhancement, unsharp
   sharpening; blur-quality score via variance of Laplacian.
2. **Scale calibration** — HOG pedestrian detection, assumed height 1.70 m, gives
   pixels-per-metre. Falls back to a default 12 m frontage assumption (flagged
   low-confidence) if no person is detected.
3. **Feature detection** — Canny edges + contour analysis (door/window candidates),
   plus a Hough-line grid-clustering pass for repetitive window grids. Contrast
   filtering rejects flat-wall false positives.
4. **Dimensional analysis** — converts pixel boxes to metres using the calibrated
   scale; classifies Window vs Door by position/aspect ratio.
5. **Output generation** — annotated overlay, scale grid/bar, validation chart
   (edge map + area bar chart), and a structured JSON report.

### Run it
```bash
pip install opencv-python numpy matplotlib
python src/facade_scale_pipeline.py path/to/image1.jpg path/to/image2.jpg
```
Outputs are written next to the script in a `results/` directory.

## 2. Interactive tool (`tool/scale_reference_tool.html`)

A standalone HTML/JS tool (open directly in any browser, no server needed):
1. Load a facade photo.
2. Calibrate scale by clicking two points spanning a known real-world distance
   (e.g. a door height ≈ 2.0 m) and entering that value.
3. Draw boxes around windows/doors/other features — dimensions are computed live.
4. Export the annotated image (PNG) and a structured dimensional report (JSON).

This exists because automatic detection (see below) is not reliable enough on its
own for arbitrary real-world photos — this tool guarantees an accurate final
output via human-verified measurements, using the same calibration→conversion
math as the automatic pipeline.

## 3. Validation summary (full detail in `docs/CV_Pipeline_Methodology_Report.md`)

Tested across 8 real facade photographs of varying quality/style:

- **Works well**: clean, high-contrast, flat facades with a regular window grid
  (e.g. `download(85)` black facade) — Hough-grid detection produced plausible
  window dimensions (~1.4–1.9 m).
- **Calibration**: when a clear pedestrian is visible and correctly detected,
  resulting door dimensions matched real-world standards (e.g. Chipperfield
  building doors: 0.79×1.74 m and 0.63×1.80 m, vs. standard ≈0.8×2.0 m — within
  ~10–15%).
- **Documented failure modes**:
  - Sculptural/recessed concrete facades → shadows and recesses mistaken for
    windows (over-detection).
  - Heavily textured brick facades → edge/line detection too noisy
    (under-detection).
  - Multiple buildings / glass reflections in frame → false positives from
    neighbouring structures.
  - No person in frame → falls back to a default scale assumption (flagged
    `fallback_default_frontage`, low confidence).

These failure modes motivated the hybrid design: automatic preprocessing +
calibration + analysis (reliable) combined with human-verified feature marking
via the interactive tool (guarantees correctness of final measurements).

## Requirements
- Python 3.10+
- `opencv-python`, `numpy`, `matplotlib`
