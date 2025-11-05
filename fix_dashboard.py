from pathlib import Path
path = Path(r"c:\Users\jpreyes\Dropbox\Workspace\sistema\paperradarai_bot\paperradar\web\static\app.js")
lines = path.read_text(encoding="utf-8").splitlines()
lines[670] = "      ? `PaperRadar · Chat ${currentChatId}`"
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
