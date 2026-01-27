@echo off
cd /d "C:\Users\uly\Vibes\SSW Times Product Summaries"
set "YTDLP_JS_RUNTIMES="
for /f "delims=" %%i in ('where node 2^>nul') do set "YTDLP_JS_RUNTIMES=node" & goto :runtimes_check_deno
:runtimes_check_deno
for /f "delims=" %%i in ('where deno 2^>nul') do (
  if defined YTDLP_JS_RUNTIMES (set "YTDLP_JS_RUNTIMES=%YTDLP_JS_RUNTIMES%,deno") else set "YTDLP_JS_RUNTIMES=deno"
)
for /f "delims=" %%i in ('where ffmpeg 2^>nul') do set "YTDLP_FFMPEG_LOCATION=%%i" & goto :ffmpeg_done
if not defined YTDLP_FFMPEG_LOCATION if exist "C:\Users\uly\AppData\Roaming\npm\node_modules\ffmpeg-static\ffmpeg.exe" set "YTDLP_FFMPEG_LOCATION=C:\Users\uly\AppData\Roaming\npm\node_modules\ffmpeg-static\ffmpeg.exe"
:ffmpeg_done
call .\.venv\Scripts\Activate.bat
python .\sprint_transcripts.py
pause
