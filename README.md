# 戲劇片頭 AI 畫風影片

可重用的 Codex 技能：把戲劇片頭、片尾或人物蒙太奇分析成分鏡，以 ImageGen 製作母圖，再重建移鏡、淡入、動態片名與真人／AI 同步對照。

片名、來源影片、畫風、尺寸、排列順序、分區比例、字幕、台標及聲音均可設定。也可以只分析分鏡、生圖、修改某一鏡或調整版面，不必每次重跑整套製作。

## 安裝

將這個倉庫放入個人 Codex skills 目錄。若同名目錄已存在，先處理現有版本，再選擇更新或另存，避免覆蓋自己的修改。

Windows PowerShell：

```powershell
git clone https://github.com/weber87na/drama-opening-ai-video.git "$env:USERPROFILE/.codex/skills/drama-opening-ai-video"
```

macOS／Linux：

```bash
git clone https://github.com/weber87na/drama-opening-ai-video.git ~/.codex/skills/drama-opening-ai-video
```

如果使用自訂 `CODEX_HOME`，改放在該目錄的 `skills/drama-opening-ai-video`。

## 使用

在 Codex 提供原片與畫風參考，例如：

> 使用 $drama-opening-ai-video 製作《新作品》。真人來源是……，畫風參考是……。我要 9:16 上下同步對照，真人在上、漫畫在下，畫面直接相接，模糊只放最上與最下。

也可指定不同需求：

> 使用 $drama-opening-ai-video，先準備 1920×1080 左右對照專案，AI 在左、真人占 45%，不要台標、字幕、模糊或聲音。這次只分析分鏡。

預設只是起點，所有設定可在專案 `project.json` 修改。特殊版型和音訊方案可以擴充；合成器需實際採用所選設定。

## 包含的方法

- 逐鏡辨識人物、場景、切點與文字事件。
- 固定母圖連續平移、兩人交錯圖層、背景固定的特寫淡入，以及前景推近後方人物。
- 等比例滿版取景、來源黑／灰邊量測、外緣補邊與中央無斷帶布局。
- screen-space／scene-space 字層、動態片名、裁切後的字幕避臉檢查。
- 使用來源影格與有理數 FPS 對齊，並檢查真正編碼的影片。

詳細入口為 [SKILL.md](SKILL.md)，其他說明按需讀取：

- [專案設定與 CLI](references/project-config.md)
- [移鏡、ImageGen 提示與字層](references/motion-and-overlays.md)
- [版面推算與交付檢查](references/layout-and-delivery.md)

## 輔助工具

需要 Python 3；`project.py` 僅使用標準函式庫。媒體檢查另需 PATH 中的 `ffprobe`。實際影像製作需要可用的原生 ImageGen，以及依專案設定建立的合成器，例如 FFmpeg／OpenCV 工作流程。

```powershell
python scripts/project.py init --project-root ./my-video --title "新作品"
python scripts/project.py inspect --project-root ./my-video --write-metadata --count-frames
python scripts/project.py validate --project-root ./my-video --mode draft
python scripts/project.py validate --project-root ./my-video --mode render-ready
```

先在 `project.json` 指定本機來源。所有專案相對路徑以 `project.json` 所在目錄為基準；重跑 `init` 保留已存在的設定。

**這個工具負責初始化、媒體資訊與資料結構檢查，不是完整渲染器，也不會下載影片、呼叫 ImageGen 或發布成片。** `render-ready` 通過不代表畫風、字幕或成片美術品質已驗收。

本倉庫只包含技能指引與工具，不包含原始劇集、生成圖片、字型、帳號憑證或現成影片。
