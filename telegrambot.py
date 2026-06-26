import logging
import os
import sys
import base64
import matplotlib
matplotlib.use("Agg")  #

from dotenv import load_dotenv  
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI  # Interacts with Google AI Studio via OpenAI 

# Load secrets from a local un-tracked .env file container
load_dotenv()

# Make Member 2's CV pipeline importable from this script
_PIPELINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_module", "src")
sys.path.insert(0, _PIPELINE_DIR)
from facade_scale_pipeline import run_pipeline

# =========================================
# 1. CONFIGURATION & CONFIG INITIALIZATION 
# =========================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GOOGLE_API_KEY = os.environ.get("GEMINI_API_KEY")

GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GOOGLE_MODEL = "gemini-3.1-flash-lite" # Can change to other available Gemini models if needed

UPLOAD_DIR = "downloads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

RESULTS_DIR = "bot_results"
os.makedirs(RESULTS_DIR, exist_ok=True)

_TOOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_module", "tool", "scale_reference_tool.html")


# =====================================================================
# HELPER UTILITIES FOR AGENT DATA PACKAGING
# =====================================================================
def _load_skill_prompt() -> str:
    """Dynamically loads Member 3's skill persona guidelines from disk."""
    if os.path.exists("skill.md"):
        with open("skill.md", "r", encoding="utf-8") as f:
            return f.read()
    return "You are an expert architectural measurement assistant."


def _encode_image_to_base64(image_path: str) -> str:
    """Converts local processed image pixels into a base64 string for LLM vision parsing."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
    

def _get_manual_tool_path() -> str:
    """Verifies the existence of the HTML asset in the repository workspace."""
    if os.path.exists(_TOOL_PATH):
        return _TOOL_PATH
    
    # Critical fallback safety: check relative root folder if script execution context shifts
    fallback_path = os.path.join("cv_module", "tool", "scale_reference_tool.html")
    if os.path.exists(fallback_path):
        return fallback_path
        
    return ""


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
# CV BRIDGE (runs Member 2's real OpenCV pipeline + Google AI Studio Layer)
# =====================================================================
def process_architectural_cv(input_image_path: str, user_caption: str = ""):
    """Run the real OpenCV pipeline and attempt to process details with Google AI Studio LLM."""
    report, annotated_path, _grid_path, chart_path, _report_path = run_pipeline(
        input_image_path, RESULTS_DIR
    )
    logger.info(f"Pipeline finished: {len(report['detected_features'])} feature(s), "
                f"calibration={report['calibration']['method']}")
    
    # Compile the default standard report as our definitive backup asset
    standard_deterministic_report = _build_report(report)

    # Check if configurations are missing or empty
    if not GOOGLE_API_KEY:
        logger.info("Google AI Studio key unconfigured or empty. Reverting to standard deterministic tracker output.")
        warning_banner = (
            "⚠️ *SYSTEM NOTICE: AI Agent Layer Offline (Unconfigured API Key).*\n"
            "_Displaying original classical computer-vision heuristic calculations directly from local memory:_\n\n"
            "-----------------------------------------\n\n"
        )
        return annotated_path, warning_banner + standard_deterministic_report, chart_path

    # Securely attempt Multimodal Agent Reasoning Request
    try:
        logger.info(f"Connecting to Google AI Studio gateway using model handle: {GOOGLE_MODEL}")
        client = OpenAI(api_key=GOOGLE_API_KEY, base_url=GOOGLE_BASE_URL)
        
        system_instructions = _load_skill_prompt()
        base64_pixels = _encode_image_to_base64(annotated_path)

        prompt_context_payload = (
            f"Analyze this architectural photo dataset framework. Below are the metrics compiled "
            f"from our local computer vision processing script:\n\n"
            f"```json\n{report}\n```\n\n"
            f"Optional User Verification Input Context: '{user_caption}'\n\n"
            f"Review the dimensions against visual elements and output your complete 5-section report layout."
        )

        response = client.chat.completions.create(
            model=GOOGLE_MODEL,
            messages=[
                {"role": "system", "content": system_instructions},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_context_payload},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_pixels}"}}
                    ]
                }
            ],
            temperature=0.2
        )
        
        agentic_llm_report = response.choices[0].message.content
        logger.info("Google AI Studio response generated successfully.")
        return annotated_path, agentic_llm_report, chart_path

    except Exception as api_exception:
            logger.error(f"⚠️ Google Studio Connection Error: {str(api_exception)}. Falling back to programmatic output.")
            warning_banner = (
                f"⚠️ *SYSTEM WARNING: Google AI Studio Agent Request Failed!*\n"
                f"*Context Data Log:*\n"
                f"```\n"
                f"{str(api_exception)}\n"
                f"```\n"
                f"_Gracefully recovering workflow and displaying original programmatic CV output records:_\n\n"
                f"-----------------------------------------\n\n"
            )
            return annotated_path, warning_banner + standard_deterministic_report, chart_path

# =====================================================================
# 2. COMMAND & USER CONTROLS HANDLERS
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


async def reject_text_only_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guardrail: Rejects inputs when users enter only captions/text updates without attaching images."""
    rejection_text = (
        "❌ *Processing Error: Missing Image Input Assets*\n\n"
        "The computer vision script requires pixel matrix data to trace geometry bounds. "
        "Please try again by uploading an actual building photo file (you can append descriptions "
        "directly into the photo caption field)."
    )
    await update.message.reply_text(rejection_text, parse_mode="Markdown")


# =====================================================================
# 3. MEDIA MESSAGE HANDLER (Core Pipeline Integration)
# =====================================================================
async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captures an uploaded image and runs it through the real CV pipeline."""
    chat_id = update.effective_chat.id
    user_caption = update.message.caption or ""
    logger.info(f"Incoming photo from Chat ID {chat_id}. Caption: '{user_caption}'")

    await update.message.reply_text("🔄 Image received. Running the computer-vision pipeline...")

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        # Step B: Download the highest-resolution version of the photo
        photo_file = await update.message.photo[-1].get_file()
        file_name = f"facade_{update.message.message_id}.jpg"
        input_path = os.path.join(UPLOAD_DIR, file_name)
        await photo_file.download_to_drive(input_path)

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)

        # Step C: Run the OpenCV pipeline + Generative AI Verification Layer
        annotated_img, report_text, chart_img = process_architectural_cv(input_path, user_caption)

        # Step D: Deliver responses cleanly back into User Interaction Space
        with open(annotated_img, 'rb') as img:
            await update.message.reply_photo(
                photo=img,
                caption="🖼️ *Annotated Image* - detected openings with dimension labels.",
                parse_mode="Markdown"
            )

        try:
            await update.message.reply_text(text=report_text, parse_mode="Markdown")
        except Exception as parse_error:
            if "Can't parse entities" in str(parse_error):
                logger.warning("AI Markdown syntax was malformed. Re-sending report as sanitized plain text.")
                await update.message.reply_text(
                    text="⚠️ *Formatting Notice:* The AI report formatting contained unclosed markdown tags. Displaying sanitized plain text report below:\n\n" + report_text
                )
            else:
                raise parse_error
            
        with open(chart_img, 'rb') as chart:
            await update.message.reply_photo(
                photo=chart,
                caption="📊 CV validation: Canny edge map + detected opening areas."
            )

        # Step E: Attach the Manual Fallback Tool asset dynamically from local folder structures
        manual_tool_file_path = _get_manual_tool_path()
        
        if manual_tool_file_path:
            call_to_action_message = (
                "🧐 *Not satisfied with the automated AI predictions?*\n\n"
                "You can execute precise manual vector alignments yourself! Download our serverless "
                "**Manual Scale Reference Tool** below. \n\n"
                "💡 *How to open:* Save the file onto your computer or phone, and simply double-click or open it "
                "with any web browser. No server hosting or installations required!"
            )
            await update.message.reply_text(text=call_to_action_message, parse_mode="Markdown")
            
            with open(manual_tool_file_path, "rb") as html_doc:
                await update.message.reply_document(
                    document=html_doc,
                    filename="Manual_Scale_Reference_Tool.html",
                    caption="📐 Tap to download and launch the client-side Manual Vector Tracker."
                )
        else:
            logger.warning(f"HTML reference tool asset not detected at expected path destination.")

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
    # Ensure variables are populated locally before launching listener
    if not TELEGRAM_BOT_TOKEN:
        print("🛑 CRITICAL ERROR: TELEGRAM_BOT_TOKEN missing from environment settings! Exiting.")
        sys.exit(1)

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reject_text_only_messages))

    print("Integration Engine online. Ready to evaluate architectural proportions...")
    app.run_polling()


if __name__ == "__main__":
    main()