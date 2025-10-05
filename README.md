# YouTube Channel Transcriber

Transcribe every video on a YouTube channel into plain text. Saves one merged file that includes each title and transcript, plus per-video `.txt` files. Uses YouTube captions first, with optional Whisper fallback.

---

## Features
- Automatically organizes transcripts by channel
- Skips videos already transcribed (via manifest tracking)
- Generates:
  - Per-video `.txt` transcripts
  - A merged `all_transcripts.txt`
  - A `manifest.jsonl` for resume support
- Optional **Whisper** transcription for videos without captions

---

## Requirements
- **Python 3.11+** (Whisper requires ≤3.11)
- **FFmpeg** installed and added to PATH
- Works on **Windows**, **macOS**, and **Linux**

---

## Installation

```bash
# Clone the repository
git clone https://github.com/<your-username>/youtube-channel-transcriber.git
cd youtube-channel-transcriber

# Create and activate a virtual environment
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
````

### Install FFmpeg

**Windows:**

```bash
winget install --id Gyan.FFmpeg -e
```

**macOS:**

```bash
brew install ffmpeg
```

**Linux:**

```bash
sudo apt install ffmpeg
```

Restart your terminal after installation.

---

## Usage

### Transcribe using existing captions (recommended first)

```bash
python transcribe_channel.py --channel "https://www.youtube.com/@moondevonyt/videos" --skip-whisper
```

### Transcribe using Whisper fallback (for videos without captions)

```bash
python transcribe_channel.py --channel "https://www.youtube.com/@moondevonyt/videos"
```

### Optional Flags

| Flag                 | Description                               |                |                    |                        |
| -------------------- | ----------------------------------------- | -------------- | ------------------ | ---------------------- |
| `--limit N`          | Only process the first N videos           |                |                    |                        |
| `--force`            | Reprocess even if already in manifest     |                |                    |                        |
| `--out-root PATH`    | Set output root directory                 |                |                    |                        |
| `--ffmpeg PATH`      | Provide directory containing `ffmpeg.exe` |                |                    |                        |
| `--model small       | medium                                    | large-v3`      | Whisper model size |                        |
| `--device cpu        | cuda`                                     | Compute device |                    |                        |
| `--compute-type auto | int8                                      | float16        | float32`           | Whisper precision mode |

---

## Output Structure

```
C:\YTChannelTranscriber\
└── Moon Dev\
    ├── txt\
    │   ├── Video Title [abc123].txt
    │   └── ...
    ├── all_transcripts.txt
    └── manifest.jsonl
```

* **`txt/`** → individual transcripts
* **`all_transcripts.txt`** → merged file of all transcripts
* **`manifest.jsonl`** → resume tracking of processed videos

---

## Resume Behavior

* Automatically skips videos that already exist in `manifest.jsonl` or `txt/`
* Use `--force` to reprocess everything
* Rebuild merged file from existing `.txt` only:

  ```bash
  python transcribe_channel.py --channel "https://example.com" --rebuild-combined
  ```

---

## Troubleshooting

* **FFmpeg not found:**
  Restart VS Code or PowerShell to reload your PATH.
  Alternatively, specify with `--ffmpeg "C:\path\to\ffmpeg\bin"`.

* **Python 3.13 Whisper errors:**
  Captions mode (`--skip-whisper`) works fine. Whisper currently requires Python ≤3.11.

---

## License

MIT License © 2025
You are free to use, modify, and distribute this project.

