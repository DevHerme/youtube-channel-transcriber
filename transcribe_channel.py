# transcribe_channel.py (resume-aware)
import os, re, sys, json, shutil, argparse
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Set

from unidecode import unidecode
from tqdm import tqdm
import webvtt
from yt_dlp import YoutubeDL

SAFE = r"[^A-Za-z0-9\-\._ ]+"

def safe_name(s: str, maxlen: int = 80) -> str:
    s = unidecode(s).strip()
    s = re.sub(SAFE, "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:maxlen].rstrip("._- ")

def vtt_to_txt(vtt_path: Path) -> str:
    lines = []
    for cue in webvtt.read(str(vtt_path)):
        t = cue.text.replace("\n", " ").strip()
        if t:
            lines.append(t)
    out, last = [], ""
    for seg in lines:
        if seg != last:
            out.append(seg)
        last = seg
    return " ".join(out).strip()

def build_ydl_params(outtmpl_dir: Path, ffmpeg_location: Optional[str] = None) -> dict:
    p = {
        "paths": {"home": str(outtmpl_dir)},
        "outtmpl": "%(title).140B [%(id)s].%(ext)s",
        "quiet": True,
        "noprogress": True,
        "ignoreerrors": True,
        "no_warnings": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "skip_download": False,
    }
    if ffmpeg_location:
        p["ffmpeg_location"] = ffmpeg_location
    return p

def get_channel_entries_and_meta(channel_url: str) -> Tuple[List[Dict], Dict]:
    ydl_opts = {
        "quiet": True,
        "noprogress": True,
        "ignoreerrors": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

    entries, meta = [], {}
    if not info:
        return entries, meta

    for e in info.get("entries") or []:
        if not e:
            continue
        if e.get("_type") == "url" and e.get("url"):
            entries.append({
                "id": e.get("id"),
                "title": e.get("title") or "",
                "webpage_url": e.get("url"),
            })

    meta = {
        "uploader": info.get("uploader") or info.get("channel") or "",
        "uploader_id": info.get("uploader_id") or info.get("channel_id") or "",
        "channel_url": info.get("webpage_url") or channel_url,
    }
    return entries, meta

def derive_channel_dir(project_root: Path, meta: dict, channel_url: str) -> Path:
    cand = meta.get("uploader") or meta.get("uploader_id") or ""
    if not cand:
        cand = channel_url.rstrip("/").split("/")[-1] or "channel"
    chan_slug = safe_name(cand, maxlen=80)
    return project_root / chan_slug

def try_download_subs(ydl_params, video_url, lang_list, outdir: Path) -> Optional[str]:
    params = dict(ydl_params)
    params.update({
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": lang_list,
        "subtitlesformat": "vtt",
    })
    with YoutubeDL(params) as ydl:
        info = ydl.extract_info(video_url, download=True)
    if not info:
        return None
    vid = info.get("id", "")
    vtts = sorted(outdir.glob(f"*{vid}*.vtt"), key=lambda p: p.stat().st_size, reverse=True)
    if not vtts:
        return None
    try:
        return vtt_to_txt(vtts[0])
    except Exception:
        return None

def download_audio(ydl_params, video_url: str, audio_dir: Path) -> Optional[Path]:
    params = dict(ydl_params)
    params.update({
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "192"}],
        "postprocessor_args": ["-ac", "1"],
        "keepvideo": False,
    })
    with YoutubeDL(params) as ydl:
        info = ydl.extract_info(video_url, download=True)
    if not info:
        return None
    title, vid = info.get("title", "video"), info.get("id", "")
    base = safe_name(f"{title} [{vid}]")
    for ext in (".m4a", ".mp3", ".opus"):
        p = audio_dir / f"{base}{ext}"
        if p.exists():
            return p
    cands = list(audio_dir.glob(f"*{vid}*.m4a")) + list(audio_dir.glob(f"*{vid}*.mp3")) + list(audio_dir.glob(f"*{vid}*.opus"))
    return max(cands, key=lambda p: p.stat().st_size) if cands else None

def whisper_transcribe(audio_path: Path, model_size="medium", device="auto", compute_type="auto") -> str:
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _ = model.transcribe(str(audio_path), vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500))
    return " ".join([s.text.strip() for s in segments]).strip()

def read_manifest_ids(manifest_path: Path) -> Set[str]:
    seen: Set[str] = set()
    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as mf:
            for line in mf:
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and obj.get("id"):
                        seen.add(obj["id"])
                except Exception:
                    continue
    return seen

def append_manifest(manifest_path: Path, rec: Dict) -> None:
    with manifest_path.open("a", encoding="utf-8") as mf:
        mf.write(json.dumps(rec, ensure_ascii=False) + "\n")

def rebuild_combined_from_txt(txt_dir: Path, combined_path: Path) -> None:
    parts = []
    for p in sorted(txt_dir.glob("*.txt")):
        title_id = p.stem
        # try recover url and title from filename
        parts.append(f"# {title_id}\n\n{p.read_text(encoding='utf-8').strip()}\n\n")
    combined_path.write_text("\n".join(parts), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--out-root", default=".")
    ap.add_argument("--model", default="medium")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--compute-type", default="auto")
    ap.add_argument("--langs", default="en,en-US")
    ap.add_argument("--skip-whisper", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ffmpeg", help="Directory containing ffmpeg.exe and ffprobe.exe")
    ap.add_argument("--force", action="store_true", help="Re-transcribe even if already in manifest or TXT exists")
    ap.add_argument("--rebuild-combined", action="store_true", help="Rebuild merged file from current TXT files and exit")
    args = ap.parse_args()

    if args.ffmpeg:
        os.environ["PATH"] = str(Path(args.ffmpeg).resolve()) + os.pathsep + os.environ["PATH"]

    project_root = Path(args.out_root).resolve()
    entries, meta = get_channel_entries_and_meta(args.channel)
    if args.limit > 0:
        entries = entries[:args.limit]
    if not entries and not args.rebuild_combined:
        print("No videos found")
        return

    channel_dir = derive_channel_dir(project_root, meta, args.channel)
    subs_dir = channel_dir / "_subs_raw"
    audio_dir = channel_dir / "_audio"
    txt_dir = channel_dir / "txt"
    for d in (subs_dir, audio_dir, txt_dir):
        d.mkdir(parents=True, exist_ok=True)

    combined_path = channel_dir / "all_transcripts.txt"
    manifest_path = channel_dir / "manifest.jsonl"

    if args.rebuild_combined:
        rebuild_combined_from_txt(txt_dir, combined_path)
        print(f"Rebuilt -> {combined_path}")
        return

    seen_ids = read_manifest_ids(manifest_path) if manifest_path.exists() else set()
    lang_list = [x.strip() for x in args.langs.split(",") if x.strip()]
    sub_params = build_ydl_params(subs_dir, args.ffmpeg)
    aud_params = build_ydl_params(audio_dir, args.ffmpeg)

    combined_parts = []
    for e in tqdm(entries, desc="Processing", unit="video"):
        title = e.get("title", "video")
        vid = e.get("id", "")
        url = e.get("webpage_url") or e.get("url")
        if not url or not vid:
            continue

        base = safe_name(f"{title} [{vid}]")
        per_txt = txt_dir / f"{base}.txt"

        if not args.force and (vid in seen_ids or (per_txt.exists() and per_txt.stat().st_size > 32)):
            # Already processed; just collect for merged output
            existing = per_txt.read_text(encoding="utf-8").strip() if per_txt.exists() else ""
            combined_parts.append(f"# {title}\n# {url}\n\n{existing}\n\n")
            if vid not in seen_ids:
                append_manifest(manifest_path, {"id": vid, "title": title, "url": url, "path": str(per_txt)})
                seen_ids.add(vid)
            continue

        txt = try_download_subs(sub_params, url, lang_list, subs_dir)
        if (not txt or len(txt) < 50) and not args.skip_whisper:
            a = download_audio(aud_params, url, audio_dir)
            if a:
                try:
                    txt = whisper_transcribe(a, model_size=args.model, device=args.device, compute_type=args.compute_type)
                except Exception:
                    txt = ""
                try:
                    a.unlink()
                except Exception:
                    pass

        if not txt:
            txt = ""

        per_txt.write_text(txt, encoding="utf-8")
        combined_parts.append(f"# {title}\n# {url}\n\n{txt}\n\n")
        append_manifest(manifest_path, {"id": vid, "title": title, "url": url, "path": str(per_txt)})
        seen_ids.add(vid)

    # append to existing combined if present to preserve prior content order
    if combined_path.exists():
        prev = combined_path.read_text(encoding="utf-8")
        combined_path.write_text(prev + ("\n" if prev and not prev.endswith("\n") else "") + "\n".join(combined_parts), encoding="utf-8")
    else:
        combined_path.write_text("\n".join(combined_parts), encoding="utf-8")

    try:
        if subs_dir.exists() and not any(subs_dir.iterdir()):
            shutil.rmtree(subs_dir)
    except Exception:
        pass

    print(f"Done -> {channel_dir}\n- Per video: {txt_dir}\n- Merged: {combined_path}\n- Manifest: {manifest_path}")

if __name__ == "__main__":
    main()
