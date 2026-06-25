# Architectural Scale Reference Assistant 🏛️📐

Architectural Scale Reference Assistant is an automated clinical spatial tool built as a Telegram bot. It utilizes computer vision (CV) and multimodal vision-language models (Vision LLM) to help architecture students and designers extract accurate spatial metrics, trace opening geometries, and analyze structural proportions from secondary visual sources like site photographs or historical archives.

This project was developed for the WID3013 Practical Computer Vision Skill assignment.

---

## 🚀 Features

* **Automated Facade Analyzer:** Processes images of building facades to detect structure geometries, extracting bounding box arrays, structural lines, and local element heights.
* **Hybrid Scaling Engine:** Computes real-world dimensions by dynamically running human vector tracking (assuming a standard 1.70m reference height) or deploying a smart fallback default frontage calibration.
* **On-Demand Manual Tool Verification:** Automatically compiles and delivers a standalone, serverless client-side HTML tool directly to the user's chat thread. Users can double-click this file to perform precise manual canvas vector tracking in any standard web browser with no server installations required.
* **Fault-Tolerant Reporting:** Generates deep architectural summaries protected by formatting gatekeepers that intercept malformed AI text syntax, auto-converting data streams to plain text to ensure 100% application uptime.

---

## 🛠️ System Workflows

### 1. Architectural Automated Workflow
1. **User Upload:** The user uploads a clear facade photograph (with an optional text verification caption) to the Telegram bot interface.
2. **Local CV Preprocessing:** The image passes through Member 2's pipeline, triggering Laplacian blur variance calculations, grayscale matrix conversions, and automated element boundaries tracing. Diagnostic validation charts (Canny edge mapping, region density distributions) are sent back to the chat window immediately.
3. **Multimodal Agent Evaluation:** The bot bundles the computed OpenCV metrics, Member 3's expert structural guidelines (`skill.md`), the user text context, and a base64-encoded visual image matrix into a single unified API payload sent directly to Google AI Studio.
4. **Crash-Proof Formatting Delivery:** The backend processes the prompt inside a high-speed forward pass. If the generative model drops structural Markdown characters while parsing deep element arrays (such as complex 28-feature detections), the bot intercepts the parsing exception and delivers a sanitized plain text report to avoid loop crashes.

### 2. Serverless Verification Workflow
1. **On-Demand Tool Injection:** Along with the automated calculations, the bot checks the repository directory tree dynamically.
2. **Asset Packaging:** It extracts the pure standalone `scale_reference_tool.html` file from the repository paths and ships it as a downloadable native document asset directly to the user's Telegram panel.
3. **Local Vector Alignment:** The user downloads the document and runs it locally inside any phone or computer browser via the `file://` protocol. The tool uses HTML5 Canvas and client-side `FileReader` loops, enabling users to click, calibrate custom reference markers (e.g., matching a door or brick course), and map out exact window ratios with 0% cloud dependencies.

---

## 🛡️ Edge-Case Error Handling & System Guardrails

To ensure stable operation during evaluations, the integration controller contains defensive programming blocks to gracefully manage data anomalies, input errors, and server infrastructure drops:

### 1. Low-Quality Input Images (Blur, Dark, Low-Res)
* **Blur Verification:** The system computes the variance of the Laplacian across the pixel grid. If the sharpness score falls below the baseline threshold, the bot does not crash; instead, it appends a `⚠️ Low Quality / Blurry Image` flag to the dataset, warns the user, and flags the measurements as *Low Confidence*.
* **Underexposure & Dark Facades:** Dark images with flat histograms limit structural edge detection. The system flags bad contrast through programmatic quality evaluation before sending data to the AI model, prompting the user to supply brighter, straight-on imagery.
* **Low Resolution / Downscaling Safety:** High-resolution assets can hit token limits, while extremely tiny assets break pixel calculations. The bot safely standardizes image scales via an aspect-ratio preserving max-width gatekeeper array before encoding the binary payload into a Base64 string.

### 2. Guardrails Against Missing Inputs (Text-Only Violation)
* **Strict Media Filters:** The system separates incoming data traffic through strict Telegram framework handlers. If a user inputs text descriptions, manual scaling queries, or random conversations *without* attaching an actual image file, the bot actively triggers a message filter block. 
* **The Rejection Trigger:** It safely rejects the text-only request with a clean markdown error message, informing the user that the underlying OpenCV matrix code cannot process geometry parameters without image asset pixels.

### 3. API Key Exception Recovery & Offline Mode
* **Missing or Expired Token Hook:** If the `.env` file does not contain a valid `GEMINI_API_KEY` (or if Google's proxy endpoints throw a network timeout exception), the bot intercepts the error background crash thread.
* **Deterministic Local Fallback:** Instead of going offline, the code activates a fallback gatekeeper banner. It drops the cloud dependence layer entirely and relies strictly on local computer memory to generate and display the original classical computer-vision calculation table, ensuring the bot stays online and remains fully functional.

## ⚙️ Setup and Installation

### Prerequisites
* **Python 3.10+**
* An active terminal interface environment.

### 1. Clone the Repository
```bash
git clone [https://github.com/yourusername/Architectural-Scale-Assistant.git](https://github.com/yourusername/Architectural-Scale-Assistant.git)
cd Architectural-Scale-Assistant
```

### 2. Create and Activate a Virtual Environment
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On Mac/Linux:
source venv/bin/activate
```

### 3. Install Python Dependencies
```bash
pip install python-telegram-bot openai opencv-python-headless matplotlib python-dotenv
```
*Note: We explicitly utilize opencv-python-headless to eliminate missing display driver exceptions during remote cloud executions.


### 4. API Key Acquisition
You need two API keys to run this bot:
1. **Telegram Bot Token**:
   - Open Telegram and search for **@BotFather**.
   - Send `/newbot` and follow the instructions to name your bot.
   - Once created, BotFather will give you a token (e.g., `123456789:ABCdefGHI...`).
2. **OpenRouter API Key**:
   - Navigate to the developer workspace at aistudio.google.com.
   - Click **"Get API key"** followed by **"Create API key in new project"**.
   - Copy the free developer token (prefixed with `AIzaSy...`). 

### 5. Environment Configuration
Create a new `.env` file or rename the `.env.example` provided.
```bash
cp .env.example .env
```
Open `.env` in your editor and paste in your API keys:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GOOGLE_API_KEY=your_google_ai_studio_api_key_here
```
*(You can also configure `BOT_MODE=dev` or `BOT_MODE=prod` to toggle the visibility of CV visuals and OCR text in the chat).*

### 6. Run the Bot
```bash
python telegrambot.py
```
You should see `Integration Engine online. Ready to evaluate architectural proportions...` in your console. Open your bot in Telegram, send `/start`, and begin uploading architectural photographs!

---

## Disclaimer & Limitations

This system is an approximate design reference tool developed exclusively for student research and academic review. It does NOT replace professional architectural surveying, structural diagnostics, or official engineering workflows. Measurements are visual estimations and should not be used for construction or safety-critical evaluations.