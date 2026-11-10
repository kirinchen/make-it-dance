# make-it-dance

一張角色圖 + 一支人跳舞的影片 → 你的角色跳同一支舞。

給 [Claude Code](https://claude.com/claude-code)(含 Claude Desktop 的 Code 分頁)用的 skill。
底層打 [fal.ai](https://fal.ai) 的動作轉移(wan-motion),**按次付費**:不用 SaaS 訂閱、不用自己的顯卡、不用 ComfyUI。

實測:3 歲卡通小孩跳 16 秒,總共 **$1.41**(含兩次重生角色圖)。

## 安裝

```bash
git clone https://github.com/kirinchen/make-it-dance ~/.claude/skills/make-it-dance
```

Windows:clone 到 `%USERPROFILE%\.claude\skills\make-it-dance`。

另外需要:

1. [uv](https://docs.astral.sh/uv/)(會自己裝 Python 和套件)
2. fal.ai 的 API key → 設成環境變數 `FAL_KEY`(設完重開 Claude)

## 用法

在 Claude Code 裡直接講:

> 用 make-it-dance 這個 skill 幫我做一支跳舞影片:主角是一個胖嘟嘟的三歲小孩,穿黑色連帽衫和白球鞋,跳這個資料夾裡 dance.mp4 的前 16 秒。先給我看角色圖,我說 OK 再生影片,最後告訴我總共花多少錢。

Claude 會照 [SKILL.md](SKILL.md) 的流程:生角色圖 → 給你看 → 動作轉移 → 回報花費。
每一步都先試算金額,你確認才真的花錢。

也可以自己跑腳本:

```bash
uv run scripts/dance.py character --describe "a chubby 3-year-old toddler in a black hoodie" --out work --live
uv run scripts/dance.py dance --character work/character.png --drive dance.mp4 --start 0 --dur 16 \
  --prompt "a chubby cartoon toddler in a black hoodie, 3D animated style. No other people, no text" --out work --live
uv run scripts/dance.py cost --out work
```

不加 `--live` 就只是試算,不花錢。

## 花費(2026-11 牌價)

| 步驟 | 價格 |
|---|---|
| 角色圖(nano-banana-pro) | $0.15 / 張 |
| 動作轉移(wan-motion) | $0.06 / 秒 |

## 注意

- 舞蹈影片請用自己拍的或有授權的;成品只留動作,沒有聲音(音樂上片時在平台裡加)
- 場景要畫在角色圖裡:成品的背景就是角色圖的背景
- 寫實風的小孩 / 真人臉容易被 fal 內容審查擋下,預設用 3D 卡通風

## License

MIT
