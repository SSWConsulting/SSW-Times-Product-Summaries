# Sprint transcript extractor + product summaries

Creates one `.txt` transcript file per "Sprint" video published in the last 30 days
from the hardcoded YouTube playlists, then generates a per-product summary file
using the OpenAI API.

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run
```powershell
python .\sprint_transcripts.py
```

The script will read `OPENAI_API_KEY` (and optional `OPENAI_MODEL`) from your
user environment variables. If you prefer a local file, it will also read from a
`.env` file if present. You can copy `.env.example` to `.env` and fill in your key:
```powershell
Copy-Item .env.example .env
```

Or set the environment variables for just this session:
```powershell
$env:OPENAI_API_KEY="YOUR_KEY_HERE"
# optional: choose a different model
# $env:OPENAI_MODEL="gpt-5"
# optional: tell yt-dlp which JS runtimes to try (comma-separated)
# $env:YTDLP_JS_RUNTIMES="node,deno"
# optional: point yt-dlp at ffmpeg if it's not on PATH
# $env:YTDLP_FFMPEG_LOCATION="C:\Path\To\ffmpeg\bin"
```

Output folder: a subfolder named with the run date (YYYY-MM-DD) in the current directory.

## Prompt customization
The summary prompt is loaded from `prompt.txt` in the project folder if present.
You can edit this file to tweak the bullet style. The template supports:
- `{product}` for the product name
- `{max_bullets}` for the current bullet limit
