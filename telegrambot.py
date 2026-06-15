import logging
import os
import sys

import matplotlib
matplotlib.use("Agg")  # headless backend: lets the CV pipeline save charts inside the bot

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Make Member 2's CV pipeline importable from this script
_PIPELINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_module", "src")
sys.path.insert(0, _PIPELINE_DIR)
from facade_scale_pipeline import run_pipeline

# =====================================================================
# 1. CONFIGURATION & CONFIG INITIALIZATION
# =====================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8630864394:AAH6tRYNSJQse9cdekiJWOq0qamH7dnNoTI"
LOG_CHANNEL_ID = -1003906150002

UPLOAD_DIR = "downloads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

RESULTS_DIR = "bot_results"
os.makedirs(RESULTS_DIR, exist_ok=True)


# =====================================================================
# REPORT BUILDER (turns the pipeline's real JSON into the skill.md format)
# =====================================================================
def _confidence_for(calibration: dict, quality_flag: str) -> str:
    """Derive an overall confidence rating from how the scale was calibrated."""
    if calibration["method"] == "fallback_default_frontage":
        return "Low"   # no person found -> rough 12m-frontage guess
    if quality_flag != "ok":
        return "Low"   # blurred image
    return "High"      # person detected + decent quality


def _build_report(report: dict) -> str:
    """Build the 5-section text report from the pipeline's structured output."""
    quality = report["image_quality"]
    calib = report["calibration"]
    features = report["detected_features"]
    blur = quality["blur_variance_laplacian"]
    flag = quality["quality_flag"]
    conf = _confidence_for(calib, flag)

    # --- Section 1: Image Quality Assessment ---
    if flag == "ok":
        sec1 = f"✅ *Usable.* Sharpness score {blur:.0f} - structural lines are clear enough to analyse."
    else:
        sec1 = (f"⚠️ *Low quality.* Sharpness score {blur:.0f} - the image looks blurred, so estimates "
                f"may be unreliable. A sharper, straight-on photo would help.")

    # --- Section 3: Dimension Table (monospace so columns line up in Telegram) ---
    if features:
        rows = ["Feature   Width    Height   Conf",
                "-------   ------   ------   ----"]
        for f in features:
            rows.append(f"{f['type']:<7}   {f['width_m']:>4.2f}m   {f['height_m']:>4.2f}m   {conf}")
        table = "```\n" + "\n".join(rows) + "\n```"
        sec3 = f"Detected *{len(features)}* opening(s):\n{table}"
    else:
        sec3 = ("No standard openings (windows/doors) were detected. Try a clearer, straight-on photo "
                "of a flat facade with a visible window grid.")

    # --- Section 4: Calibration Note ---
    ppm = calib["pixels_per_metre"]
    if calib["method"] == "person_detection":
        sec4 = (f"Reference: a *detected person* (assumed 1.70 m tall) gives a scale of {ppm:.1f} "
                f"pixels/metre. All sizes are calculated proportionally from this. Confidence: *{conf}*.")
    else:
        sec4 = (f"⚠️ No person was found for scale, so the system assumed a *12 m building frontage* "
                f"({ppm:.1f} pixels/metre). This is a rough fallback - treat all sizes as *Low confidence*.")

    # --- Section 5: Recommendations ---
    recs = []
    if features:
        recs.append("• Use these proportions as a design reference for baseline elevations - not for construction.")
    if calib["method"] == "fallback_default_frontage":
        recs.append("• For better accuracy, retake the photo with a person standing in frame for scale.")
    if flag != "ok":
        recs.append("• The image is blurred - a sharper photo will improve detection.")
    if not features:
        recs.append("• No openings detected - this facade may be too textured (e.g. brick) or shot at too steep an angle.")
    if not recs:
        recs.append("• Looks good - proportions are usable for design reference.")
    sec5 = "\n".join(recs)

    return (
        "*1. Image Quality Assessment*\n" + sec1 + "\n\n"
        "*3. Dimension Table*\n" + sec3 + "\n\n"
        "*4. Calibration Note*\n" + sec4 + "\n\n"
        "*5. Recommendations*\n" + sec5 + "\n\n"
        "All measurements are approximate visual estimates for design reference only - "
        "not for construction or surveying."
    )


# =====================================================================
# CV BRIDGE (runs Member 2's real OpenCV pipeline)
# =====================================================================
def process_architectural_cv(input_image_path: str):
    """Run the real OpenCV pipeline and build a report from its actual output.

    Returns (annotated_image_path, report_text, validation_chart_path).
    """
    report, annotated_path, _grid_path, chart_path, _report_path = run_pipeline(
        input_image_path, RESULTS_DIR
    )
    logger.info(f"Pipeline finished: {len(report['detected_features'])} feature(s), "
                f"calibration={report['calibration']['method']}")
    return annotated_path, _build_report(report), chart_path


# =====================================================================
# 2. COMMAND HANDLERS
# =====================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets users and details the exact system constraints and ethical guidelines."""
    welcome_text = (
        "🏛️ *Welcome to the Architectural Scale Reference Assistant*\n\n"
        "I estimate approximate building dimensions and structural proportions from a facade photo.\n\n"
        "📥 *How to use:* Upload a clear, straight-on building photo. For best results the photo should "
        "be sharp, flat-on, and ideally have a person visible (used to calibrate the scale).\n\n"
        "⚠️ All measurements are approximate visual estimates for design reference only. "
        "This tool does NOT replace professional surveying or engineering. Do NOT use it for construction."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


# =====================================================================
# 3. MEDIA MESSAGE HANDLER (Core Pipeline Integration)
# =====================================================================
async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captures an uploaded image and runs it through the real CV pipeline."""
    chat_id = update.effective_chat.id
    user_caption = update.message.caption or ""
    logger.info(f"Incoming photo. Caption: '{user_caption}'")

    await update.message.reply_text("🔄 Image received. Running the computer-vision pipeline...")

    try:
        # Step A: Forward the raw upload to the private team log channel
        await context.bot.forward_message(
            chat_id=LOG_CHANNEL_ID,
            from_chat_id=chat_id,
            message_id=update.message.message_id
        )

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        # Step B: Download the highest-resolution version of the photo
        photo_file = await update.message.photo[-1].get_file()
        file_name = f"facade_{update.message.message_id}.jpg"
        input_path = os.path.join(UPLOAD_DIR, file_name)
        await photo_file.download_to_drive(input_path)

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)

        # Step C: Run the real OpenCV pipeline
        annotated_img, report_text, chart_img = process_architectural_cv(input_path)

        # Step D: Send the annotated image, then the report, then the validation chart
        with open(annotated_img, 'rb') as img:
            await update.message.reply_photo(
                photo=img,
                caption="🖼️ *Annotated Image* - detected openings with dimension labels.",
                parse_mode="Markdown"
            )

        await update.message.reply_text(text=report_text, parse_mode="Markdown")

        with open(chart_img, 'rb') as chart:
            await update.message.reply_photo(
                photo=chart,
                caption="📊 CV validation: Canny edge map + detected opening areas."
            )

    except Exception as e:
        logger.error(f"Workflow crash: {str(e)}", exc_info=True)
        await update.message.reply_text(
            "❌ Error processing your request. Please ensure you uploaded a valid, clear image file."
        )


# =====================================================================
# 4. RUNNER APPLICATION
# =====================================================================
def main():
    """Launches the central polling application engine."""
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_upload))

    print("🚀 Integration Engine online. Ready to evaluate architectural proportions...")
    app.run_polling()


if __name__ == "__main__":
    main()
