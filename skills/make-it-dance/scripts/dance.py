# /// script
# requires-python = ">=3.10"
# dependencies = ["av>=12", "truststore>=0.9"]
# ///
"""make-it-dance:一張角色圖 + 一支跳舞影片 → 你的角色跳同一支舞(fal.ai 動作轉移)。

不用 SaaS 訂閱、不用自己的顯卡、不用 ComfyUI —— 只要一把 fal API key,按次付費。

    uv run dance.py character --describe "a chubby 3-year-old toddler ..." --out work/
    uv run dance.py dance --character work/character.png --drive dance.mp4 \\
        --start 0 --dur 16 --prompt "..." --out work/
    uv run dance.py cost --out work/

**預設是 dry-run**:只印要做什麼、估多少錢,不花錢。加 `--live` 才真的打 API。
key 讀環境變數 `FAL_KEY`(或 `FAL_API_KEY`)。

為什麼這樣設計(都是我們真的踩過、花錢買到的):
1. 角色先在「圖」這層定案:一張圖 $0.15,一支影片 $1 起跳。圖不對就重生圖,別拿影片試錯。
2. prompt 一定要送:不送的話 fal 會自己填「视频中的人在做动作」,角色就往「人」那邊長
   (我們的貓因此長出白色袖子)。
3. 驅動影片先壓成 24fps、拿掉聲音:計費以 24fps 換算秒數;60fps 原檔有被多算的風險,
   聲音模型也用不到。
4. 角色圖要「站著、全身入鏡、手臂看得到」:坐著的角色會被硬拉長手腳去配人的舞步。
5. 場景要畫進角色圖:wan-motion 的背景沿用角色圖,prompt 裡寫的場景不會生效。
6. 預設 3D 卡通風、穿好衣服:寫實風的小孩會被 fal 內容審查擋下(錢照扣)。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

try:   # 用作業系統的憑證庫 —— uv 裝的 Python 在 Windows 上找不到 CA,下載會 SSL 失敗
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

QUEUE = "https://queue.fal.run"
UPLOAD_INITIATE = "https://rest.alpha.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3"

IMAGE_MODEL = "fal-ai/nano-banana-pro"     # 文生圖,$0.15 / 張
MOTION_MODEL = "fal-ai/wan-motion"          # 動作轉移,$0.06 / 影片秒(以 24fps 計)
USD_PER_IMAGE = 0.15
USD_PER_SEC = 0.06
MAX_WAIT = 2400                             # 動作轉移很慢:16 秒的片實測要 ~20 分鐘

DEFAULT_STYLE = "3D animated movie character render, stylized CGI, soft smooth shading"
DEFAULT_SCENE = "a clean bright empty dance studio with a light wooden floor"
CHARACTER_TEMPLATE = (
    "{describe}, fully clothed (top, pants and shoes). Full body in frame from head to feet, "
    "standing upright and facing the camera, both arms relaxed at the sides and fully visible. "
    "Standing in {scene}, soft even lighting. {style}, vertical 9:16 composition. "
    "Only this one character, no text, no watermark."
)


# ── 小工具 ────────────────────────────────────────────────────────────────
def key() -> str:
    k = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
    if not k:
        sys.exit("找不到 FAL_KEY 環境變數。到 fal.ai 建一把 API key,設成環境變數 FAL_KEY 再跑。")
    return k


def http(method: str, url: str, body: dict | None = None, timeout: int = 60, headers: bool = False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Key {key()}",          # fal 用 "Key",不是 "Bearer"
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read() or b"{}")
            return (out, r.headers) if headers else out
    except urllib.error.HTTPError as e:
        msg = e.read()[:300].decode("utf-8", "replace")
        if "content_policy" in msg:
            sys.exit(f"被 fal 內容審查擋下(錢可能已扣)。寫實風的小孩 / 真人最容易被擋 —— "
                     f"改用預設的 3D 卡通風,或換描述。\n{msg}")
        sys.exit(f"fal 回 HTTP {e.code}:{msg}")


def upload(path: Path) -> str:
    """本機檔 → fal storage URL(模型只吃 URL)。"""
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    info = http("POST", UPLOAD_INITIATE, {"content_type": ctype, "file_name": path.name})
    put = urllib.request.Request(info["upload_url"], data=path.read_bytes(), method="PUT",
                                 headers={"Content-Type": ctype})
    urllib.request.urlopen(put, timeout=300).read()
    return info["file_url"]


def run_model(model: str, payload: dict, max_wait: int) -> dict:
    """送進 fal 佇列 → 等 → 拿結果。中途斷線也能用 request_id 回去撈。"""
    sub = http("POST", f"{QUEUE}/{model}", payload)
    rid = sub["request_id"]
    status_url = sub.get("status_url") or f"{QUEUE}/{model}/requests/{rid}/status"
    result_url = sub.get("response_url") or f"{QUEUE}/{model}/requests/{rid}"
    print(f"  已送出 request_id={rid}(錢從這一刻開始算)")
    t0 = time.time()
    while True:
        st = http("GET", status_url).get("status")
        el = int(time.time() - t0)
        print(f"  …{el // 60}:{el % 60:02d} {st}", flush=True)
        if st == "COMPLETED":
            res, hdrs = http("GET", result_url, headers=True)
            # fal 只在**第一次**取結果時附上實際計費單位 —— 錯過就只能去後台翻
            res["_billable_units"] = hdrs.get("x-fal-billable-units")
            res["_request_id"] = rid
            return res
        if st not in ("IN_QUEUE", "IN_PROGRESS"):
            sys.exit(f"fal 狀態異常:{st}(request_id={rid})")
        if el > max_wait:
            sys.exit(f"等超過 {max_wait // 60} 分鐘還沒好。錢已經扣了 —— 之後用 request_id={rid} 去撈:{result_url}")
        time.sleep(15)


def download(url: str, dest: Path) -> Path:
    with urllib.request.urlopen(url, timeout=300) as r:
        dest.write_bytes(r.read())
    return dest


def ledger_add(out: Path, step: str, usd: float, **extra):
    f = out / "cost.json"
    rows = json.loads(f.read_text("utf-8")) if f.exists() else []
    rows.append({"at": datetime.now().isoformat(timespec="seconds"), "step": step, "usd": round(usd, 3), **extra})
    f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")


def cut_drive(src: Path, dst: Path, start: float, dur: float, fps: int = 24) -> float:
    """剪一段、壓成 24fps、拿掉聲音、最長邊壓到 1280。回實際秒數。"""
    import av
    from fractions import Fraction
    inp = av.open(str(src))
    vs = inp.streams.video[0]
    w, h = vs.width, vs.height
    s = min(1.0, 1280 / max(w, h))
    W, H = int(w * s) // 2 * 2, int(h * s) // 2 * 2
    out = av.open(str(dst), "w")
    os_ = out.add_stream("libx264", rate=fps)
    os_.width, os_.height, os_.pix_fmt = W, H, "yuv420p"
    os_.options = {"crf": "18"}
    inp.seek(int(start / vs.time_base), stream=vs)
    n, total = 0, int(round(dur * fps))
    for fr in inp.decode(vs):
        if fr.time is None or fr.time < start + n / fps:
            continue
        if n >= total:
            break
        img = fr.reformat(width=W, height=H, format="yuv420p")
        img.pts, img.time_base = n, Fraction(1, fps)
        for p in os_.encode(img):
            out.mux(p)
        n += 1
    for p in os_.encode():
        out.mux(p)
    out.close(); inp.close()
    return n / fps


# ── 指令 ──────────────────────────────────────────────────────────────────
def cmd_character(a):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    prompt = CHARACTER_TEMPLATE.format(describe=a.describe.rstrip("."), scene=a.scene, style=a.style)
    print(f"① 生角色圖({IMAGE_MODEL})")
    print(f"   prompt:{prompt}")
    print(f"   預估:${USD_PER_IMAGE:.2f}")
    if not a.live:
        print("\n(dry-run,沒花錢。確認後加 --live)")
        return
    res = run_model(IMAGE_MODEL, {"prompt": prompt, "aspect_ratio": "9:16", "num_images": 1}, 600)
    dest = out / (a.name or "character.png")
    download(res["images"][0]["url"], dest)
    ledger_add(out, "character", USD_PER_IMAGE, model=IMAGE_MODEL, file=dest.name,
               request_id=res["_request_id"], billable_units=res["_billable_units"])
    print(f"\n✅ 角色圖:{dest}\n   先打開看:站著?全身?手臂看得到?衣服穿好?背景是你要的場景?"
          f"不對就改描述重生 —— 圖便宜,影片貴。")


def cmd_dance(a):
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    char, drive = Path(a.character), Path(a.drive)
    for p in (char, drive):
        if not p.exists():
            sys.exit(f"找不到檔案:{p}")
    if not a.prompt.strip():
        sys.exit("--prompt 必填。不送 prompt,fal 會預設成「视频中的人」,角色會往人那邊長。")
    cut = out / "drive-24fps.mp4"
    print(f"② 剪驅動影片:{drive.name} 第 {a.start}s 起 {a.dur}s → 24fps、無聲")
    sec = cut_drive(drive, cut, a.start, a.dur)
    est = sec * USD_PER_SEC
    print(f"   實際 {sec:.2f}s → {cut}")
    print(f"③ 動作轉移({MOTION_MODEL})")
    print(f"   角色圖:{char}")
    print(f"   prompt:{a.prompt}")
    print(f"   預估:{sec:.2f}s × ${USD_PER_SEC}/s = ${est:.2f}(要等 15–25 分鐘)")
    if not a.live:
        print("\n(dry-run,沒花錢。確認後加 --live)")
        return
    print("   上傳角色圖 / 驅動影片…")
    payload = {"image_url": upload(char), "video_url": upload(cut), "prompt": a.prompt,
               "adapt_motion": True}            # 把人的動作適配到角色體型
    res = run_model(MOTION_MODEL, payload, MAX_WAIT)
    dest = out / (a.name or "dance.mp4")
    download(res["video"]["url"], dest)
    ledger_add(out, "dance", est, model=MOTION_MODEL, seconds=round(sec, 2), file=dest.name,
               request_id=res["_request_id"], billable_units=res["_billable_units"])
    print(f"\n✅ 成品:{dest}\n   從頭看到尾:手腳比例、臉有沒有換人、有沒有多出一個人。")
    cmd_cost(a)


def cmd_cost(a):
    f = Path(a.out) / "cost.json"
    rows = json.loads(f.read_text("utf-8")) if f.exists() else []
    if not rows:
        print("還沒花錢。"); return
    print("\n花費(依牌價估;精確實收看 fal 後台 Billing):")
    for r in rows:
        print(f"  {r['at']}  {r['step']:<9} ${r['usd']:.3f}  {r.get('file', '')}")
    print(f"  合計 ${sum(r['usd'] for r in rows):.2f}")


def main():
    # Windows 主控台預設 cp950 / cp1252,中文會變亂碼 —— 一律改成 UTF-8 輸出
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="一張角色圖 + 一支跳舞影片 → 你的角色跳同一支舞")
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("character", help="用文字生一張角色圖($0.15)")
    c.add_argument("--describe", required=True, help="角色長相(英文較穩)")
    c.add_argument("--scene", default=DEFAULT_SCENE, help="場景 —— 會直接成為成品影片的背景")
    c.add_argument("--style", default=DEFAULT_STYLE, help="畫風(預設 3D 卡通;寫實風的小孩會被審查擋)")
    d = sp.add_parser("dance", help="角色圖 + 驅動影片 → 跳舞影片($0.06/秒)")
    d.add_argument("--character", required=True)
    d.add_argument("--drive", required=True, help="跳舞影片(人跳的,全身入鏡、鏡頭不晃最好)")
    d.add_argument("--start", type=float, default=0.0)
    d.add_argument("--dur", type=float, default=10.0)
    d.add_argument("--prompt", required=True, help="描述角色長相 + 畫風(一定要寫;場景以角色圖為準)")
    k = sp.add_parser("cost", help="看這個資料夾花了多少")
    for p in (c, d, k):
        p.add_argument("--out", default="work")
    for p in (c, d):
        p.add_argument("--name", default="")
        p.add_argument("--live", action="store_true", help="真的打 API(會花錢)")
    a = ap.parse_args()
    {"character": cmd_character, "dance": cmd_dance, "cost": cmd_cost}[a.cmd](a)


if __name__ == "__main__":
    main()
