---
name: make-it-dance
description: 一張角色圖 + 一支人跳舞的影片 → 讓你的角色(寵物、寶寶、公仔、原創角色)跳同一支舞。用 fal.ai 的動作轉移(wan-motion),按次付費,不用 SaaS 訂閱、不用顯卡、不用 ComfyUI。使用者說「讓 X 跳這支舞」「做跳舞影片」「動作轉移」時用。
---

# make-it-dance

把一支人跳舞的影片的**動作**,搬到你的角色身上。成品是無聲直式影片,音樂上片時在 Shorts / Reels 裡加。

## 你需要

- `uv`(https://docs.astral.sh/uv/ —— 它會自己裝 Python 跟 PyAV)
- fal.ai API key,設成環境變數 `FAL_KEY`(**不要貼進對話**)
- 一支跳舞影片:全身入鏡、鏡頭不晃、一個人。用你自己拍的或有授權的;成品只留動作

## 花費(牌價,2026-11)

| 步驟 | 模型 | 價格 |
|---|---|---|
| 生角色圖(沒有現成圖才要) | nano-banana-pro | $0.15 / 張 |
| 動作轉移 | wan-motion | $0.06 / 秒(16 秒 ≈ $0.96) |

## 流程(照順序,每一步先 dry-run)

`scripts/dance.py` 在**這個 skill 的資料夾**底下(載入 skill 時給的 base directory);下面指令裡的 `scripts/dance.py` 要換成完整路徑。它預設 **dry-run**:只印計畫跟預估金額,不花錢。使用者確認後才加 `--live`。

### 1. 角色圖 —— 在便宜的這層定案

有現成圖就跳過。沒有就生一張:

```bash
uv run scripts/dance.py character --describe "<角色長相,英文>" --scene "<場景>" --out work
uv run scripts/dance.py character --describe "<同上>" --scene "<同上>" --out work --live
```

- `--scene`:**場景要在這裡定** —— 成品影片的背景就是角色圖的背景,動作轉移的 prompt 改不了場景
- `--style`:預設 3D 卡通風。**寫實風的小孩 / 真人臉會被 fal 內容審查擋下**(錢照扣),不要改成 photorealistic
- 模板已經要求「衣服穿好」;還是要看一眼(我們第一張小孩只穿內褲)

生完**一定打開來看**,不對就改描述重生(一張 $0.15,影片一支 $1 起跳):
- 站著、全身入鏡、兩隻手臂看得到 —— 坐著或手被擋住,模型會硬拉長手腳去配人的舞步
- 衣服穿好、背景就是你要的場景

### 2. 動作轉移

```bash
uv run scripts/dance.py dance --character work/character.png --drive <舞蹈影片.mp4> \
  --start <開始秒> --dur <秒數> --prompt "<角色 + 畫風描述>" --out work
# 確認金額後加 --live
```

- **`--prompt` 一定要寫**:寫角色長相 + 畫風(跟角色圖一致)+ 「No other people, no text」。
  不寫的話 fal 預設填「视频中的人在做动作」,角色會往人類長(我們的貓因此長出白袖子)。
- 第一次先跑短一點(`--dur 5`,約 $0.30)看效果,再跑整段。
- 要等 15–25 分鐘。中途斷掉,錢照扣;終端印過的 `request_id` 可以拿去撈結果。

### 3. 驗收

整支看完(不要只看一格):手腳比例對不對、臉有沒有中途換掉、有沒有多出一個人、動作有沒有跟上拍子。

### 4. 看花多少

```bash
uv run scripts/dance.py cost --out work
```

帳本 `work/cost.json` 會記每一筆的 `request_id` 和 fal 回的實際計費單位(`billable_units`)。

## 為什麼這樣做(都是踩過的坑)

| 坑 | 解法 |
|---|---|
| 文生影片做不出指定舞步,第二段還換了一隻角色 | 改用動作轉移:動作從真人影片來,長相從角色圖來 |
| 角色手腳被拉長 | 角色圖改成站姿、手臂看得到 |
| 角色長出人的袖子 | prompt 從沒送出去 → 一定要送 |
| 拿影片試錯很貴 | 長相在圖那層定案,影片只跑一次 |
| 60fps 的驅動影片可能被多算秒數 | 先壓成 24fps |
| prompt 寫了練舞室,背景還是角色圖的米色牆 | 場景畫進角色圖(`--scene`) |
| 寫實風小孩被內容審查擋,白花 $0.15 | 預設 3D 卡通風 |
| Windows 上下載成品 SSL 失敗(錢已扣) | 用作業系統憑證庫(truststore) |
