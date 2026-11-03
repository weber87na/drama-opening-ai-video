# 可編輯專案設定與工具

`scripts/project.py` 只做初始化、媒體檢查及結構驗證；不下載、不產圖、不渲染、不發布。需要 Python 3，`inspect` 另需 PATH 中的 ffprobe。引用本工具時以實際技能目錄的絕對路徑執行；以下命令假設工作目錄在技能資料夾。

## 開新案／續案

```powershell
python scripts/project.py init --project-root "D:/影音專案/新作品" --title "新作品"
python scripts/project.py init --project-root "D:/影音專案/橫式版本" --width 1920 --height 1080 --layout side-by-side --order ai-first --fit cover --fill none --audio none
python scripts/project.py inspect --project-root "D:/影音專案/新作品" --write-metadata --count-frames
python scripts/project.py validate --project-root "D:/影音專案/新作品" --mode draft
python scripts/project.py validate --project-root "D:/影音專案/新作品" --mode render-ready
```

新案的建議預設是1080×1920、stacked、source-first、各占一半、cover、outer-blur、沿用來源FPS與原音。每個預設都可改；片名、來源與畫風預設空白。`init` 也接受 `--source`、`--style-source`、`--style-start`、`--fps`。已有 `project.json` 時保留原檔，重新 init 不會套用新參數；續作直接編輯該檔。

所有相對路徑（包含 init/inspect 參數）相對於 **project.json 所在目錄**，不是 shell CWD。跨專案檔案也可用明確絕對路徑；輸出不可覆寫來源。網址可先記在設定，但 inspect 與素材驗證需要已取得的本機檔。

`inspect` 預設唯讀，回傳 ffprobe 事實與未執行的抽幀命令。`--write-metadata` 才保存 `source.probe`；若未設終點，會以已知媒體幀數填入。**這是素材的可用終點，還要依使用者指定片頭／片尾選取範圍**，不是自動要重製整集。

FPS、旋轉、SAR 與音軌以實測為準。首中尾 PTS 抽樣只能標記 sampled-cfr／vfr／unknown，並非全片幀節奏保證。VFR 要先建立等時長 CFR 工作檔再重新 inspect，或使用 `source.timing_strategy="pts"` 並寫會讀真實 PTS 的合成器；不能僅把輸出 FPS 填成整數就當作已轉換。

## project.json

| 欄位 | 用途 |
|---|---|
| `schema_version` | 工具資料格式版本，目前1 |
| `title` | 當次片名，無需片名可為null |
| `source.path` | 本機來源；取得之前可暫存網址 |
| `source.start_frame / end_frame` | 原始來源幀座標，`[start,end)`，不是輸出相對幀 |
| `source.crop_xyxy` | 測得的有效畫面，`[x0,y0,x1,y1]` 右下邊界不含；null表示未另裁 |
| `source.probe` | inspect保存的實測尺寸、FPS、幀數、SAR、旋轉、音軌與檔案狀態；不手造數值冒充實測 |
| `source.timing_strategy` | auto或pts；需要正規化時換成本機CFR工作檔並重新量測 |
| `style.source` | 當次風格影片／圖片來源，與真人來源各自獨立 |
| `style.start_seconds / end_seconds` | 風格參考的時間區間，不是輸出時長 |
| `style.description` | 任意畫風描述；可另外加入局部參考範圍與人物一致性設定 |
| `style.references` | 多張參考圖，路徑字串陣列或含明確 `path` 的物件陣列；本機檔會驗存在，網址仍須實際檢視 |
| `output.width / height` | 目標像素尺寸，不限建議比例 |
| `output.layout` | helper常用值stacked、side-by-side；其他版型可在專案擴充 |
| `output.order` | source-first或ai-first；左右版型的first為左方 |
| `output.source_share` | 來源內容占分割軸的比例，0與1之間；交換順序仍指來源的占比 |
| `output.fit / fill` | cover或contain；outer-blur或none。需要不同區域策略時增加專案設定，合成器必須真的採用 |
| `output.fps` | source或正有理數字串；改FPS保持時間不變，除非另外要求改速 |
| `output.audio` | helper常用值source、none；其他配樂／配音方案加上實際素材與時間映射 |
| `output.path` | 目的成片路徑，依當次作品修改，保留舊版 |
| `timeline` | 分鏡JSON路徑，預設shots.json |
| `overlays` | 全域字層／台標事件；不需要時保持空陣列 |

helper的參數選單是已支援的常用選項，並非創作限制。自訂 layout/audio/fit 等值會提示需實作；不要只改設定而沿用忽略這些值的舊渲染器。需要獨立區域的補邊、外緣尺寸、字幕顯示區域、原生書名變換或調色時，增加明確設定，由專案合成器讀取；不要塞回影片專用常數。

## shots.json 與圖層

以下只是資料結構示意，幀數和路徑必須換成實測資料，不是固定片長或命名規則：

```json
[
  {
    "id": "opening_scene",
    "start_frame": 0,
    "end_frame": 90,
    "representative_frame": 45,
    "artwork": "assets/ai/opening_scene.png",
    "motion": {
      "type": "pan",
      "coordinate_space": "normalized",
      "keyframes": []
    },
    "layers": []
  }
]
```

依當次觀察選 `motion.type` 與關鍵幀；工具不會憑 type 自動產生動畫，也不會驗證每條相機路徑。`representative_frame` 若有填，須是位於該鏡半開區間內的整數。無主母圖但有完整場景圖層時，可用非空 layers 表達。共用母圖直接引用相同檔案，不憑鏡頭編號猜關係。

`overlays`／`layers` 的基礎欄位是 `id,path,space,start_frame,end_frame`。`space` 明確為screen或scene；全域scene字層另設 `shot_id`。鏡頭內layers可省略起訖幀，沿用該鏡範圍。

可按需要擴充：`required`、`kind`、`content_source`、`text`、`target_panel`、`status`、`verified_text`、`anchor`、`keyframes`、字型與描邊。這些創作欄位由專案流程讀取，helper的檔案存在檢查不代表文字已校對或完整交付。文字尚未生成時保留待辦事件；render-ready前補齊所有required事件，不以刪掉缺項讓檢查通過。

## 驗證邊界

draft容許來源、FPS、素材及時間範圍尚待完成，會列警告；已填但矛盾的時間區間、裁切或結構仍應修正。render-ready要求來源實檔與量測、連續幀時間軸、存在的母圖／圖層及明確座標系。

此檢查不渲染，不會判斷畫風相似度、字遮臉、圖檔實際透明品質、音訊同步或自訂效果是否實作。輸出後仍按 [版面與交付檢查](layout-and-delivery.md) 驗收真正成片。需要重剪／重排／變速而非連續重製來源時，先擴充時間映射和validator；不能捏造連續幀來繞過本工具的單段連續來源假設。
