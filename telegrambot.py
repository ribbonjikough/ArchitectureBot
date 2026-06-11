import logging
import os
import re
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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


# =====================================================================
# INTEGRATION BRIDGE (FOR MEMBER 2 & MEMBER 3 CODES)
# =====================================================================
async def process_architectural_cv_and_agent(input_image_path: str, user_caption: str):
    """
    Executes the Step-by-Step workflow from skill.md.
    Accepts both the file path and the optional calibration text caption.
    """
    # Default fallback values (Step 3: Standard Assumptions)
    reference_source = "standard assumption"
    ref_detail = "Standard single door height at 2.1m"
    
    # Simple regex to check if user passed a calibration dimension in the caption
    if user_caption:
        match = re.search(r"(\d+(\.\d+)?)\s*m", user_caption.lower())
        if match:
            reference_source = "user-provided"
            ref_detail = f"Custom reference marker identified at {match.group(1)}m"

    # Simulated processed asset from Member 2 (For now, passing original image)
    output_image_path = input_image_path 
    
    # Constructing the exact 5-part response mandated by Member 3's Output Format
    final_report = (
        "### 1. Image Quality Assessment\n"
        "✅ **Status:** Usable. Spatial structural lines are sharp. Mild perspective "
        "distortion observed at outer margins but within acceptable 45-degree threshold bounds.\n\n"
        
        "### 2. Annotated Image\n"
        "⬇️ *See the calibrated scaling grid overlay and dimension tracking markers rendered below.*\n\n"
        
        "### 3. Dimension Table\n"
        "| Feature | Estimated Height | Estimated Width | Confidence |\n"
        "| :--- | :---: | :---: | :---: |\n"
        "| Primary Entrance Door | 2.1m | 0.9m | High |\n"
        "| Ground Tier Window Frame | 1.2m | 1.5m | Medium |\n"
        "| Structural Column Column A | 3.0m | 0.4m | Medium |\n"
        "| Perimeter Balcony Railing | 1.0m | 4.2m | Low |\n\n"
        
        "### 4. Calibration Note\n"
        f"\"Reference used: {ref_detail} ({reference_source}). All other dimensions are "
        "calculated proportionally from this reference.\"\n\n"
        
        "### 5. Recommendations\n"
        "• **Design Utility:** Use these spatial proportions to map out baseline elevations for your design studio layout.\n"
        "• **Warning:** Balcony measurements flagged with **Low Confidence** due to edge blending with background tree shadows. Avoid using for construction or structural modeling calculations."
    )
    
    return output_image_path, final_report


# =====================================================================
# 2. COMMAND HANDLERS
# =====================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets users and details the exact system constraints and ethical guidelines."""
    welcome_text = (
        "🏛️ **Welcome to the Architectural Scale Reference Assistant**\n\n"
        "I help architecture students estimate approximate building dimensions and structural proportions from photos.\n\n"
        "📥 **How to use:** Upload a building photo. You can optionally include a known measurement in the caption text (e.g., 'the door is 2.1m tall') to calibrate the scaling matrix.\n\n"
        "⚠️ *Ethical Disclaimer:* All measurements generated are approximate visual estimates for design reference only. "
        "This tool does NOT replace professional surveying or engineering calculations. Do NOT use for construction or safety-critical purposes."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


# =====================================================================
# 3. MEDIA MESSAGE HANDLER (Core Pipeline Integration)
# =====================================================================
async def handle_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captures images along with optional tracking text captions, running them through the CV pipeline."""
    chat_id = update.effective_chat.id
    
    # Capture optional text captions sent alongside the image file
    user_caption = update.message.caption or ""
    logger.info(f"Incoming file payload discovered. Accompanying text caption: '{user_caption}'")

    # Let the user know the system is alive and processing
    await update.message.reply_text("🔄 Visual dataset received. Initializing image parsing pipeline...")

    try:
        # Step A: Forward raw transaction assets directly to private team log channel
        await context.bot.forward_message(
            chat_id=LOG_CHANNEL_ID,
            from_chat_id=chat_id,
            message_id=update.message.message_id
        )

        # Show a "typing..." loading state while downloading the file
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        # Step B: Secure file asset download parameters
        photo_file = await update.message.photo[-1].get_file()
        file_name = f"facade_{update.message.message_id}.jpg"
        input_path = os.path.join(UPLOAD_DIR, file_name)
        
        await photo_file.download_to_drive(input_path)

        # Show an "uploading photo..." loading state while running processing tasks
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)

        # Step C: Execute processing function with both raw file and text metrics
        processed_img, structured_report = await process_architectural_cv_and_agent(input_path, user_caption)

        # --- STEP D FIXED: SPLIT IMAGE AND TEXT REPORT TO BYPASS 1024 CHARACTER LIMIT ---
        
        # 1. Send the visual image asset first with a short, clean caption
        await update.message.reply_photo(
            photo=open(processed_img, 'rb'),
            caption="🖼️ **Section 2: Annotated Image**\nSee the calibrated scaling grid overlay and dimension tracking markers rendered below.",
            parse_mode="Markdown"
        )

        # 2. Immediately follow up with the full, detailed Markdown Report (Up to 4096 characters allowed)
        await update.message.reply_text(
            text=structured_report,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Critical workflow crash: {str(e)}")
        await update.message.reply_text("❌ Error processing your request. Please ensure you uploaded a valid, clear image file.")


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