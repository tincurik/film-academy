import json
import subprocess


def probe(path):
    """(duration s, width, height, fps) of a video; ffprobe read as json (csv output differs between platforms)."""
    o = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate,codec_type", "-of", "json", str(path)],
                                  capture_output=True, text=True, check=True).stdout)
    v = [s for s in o["streams"] if s["codec_type"] == "video"][0]
    n, d = v["r_frame_rate"].split("/")
    return float(o["format"]["duration"]), v["width"], v["height"], round(float(n) / float(d), 2)


def duration(path):
    return float(json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                                           capture_output=True, text=True, check=True).stdout)["format"]["duration"])
