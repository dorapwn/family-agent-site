# 家庭 AI 助理 — 使用指南網站

**Public site.** 呢度載嘅係畀用戶睇嘅內容：學業 / 家務 / 工作 / 玩樂四份指南。

Persona（語氣、界線、記憶範圍）喺另一個 **private** repo：`dorapwn/family-agent-guides`。
兩邊唔好混：呢個 repo 唔應該出現任何個人資料、客戶資料、成員個人資料。

---

## 結構

```
family-agent-site/
├── index.html            主頁（ASCII 動畫 hero + 四張卡）
├── study.html            01 學業
├── home.html             02 家務
├── work.html             03 工作
├── fun.html              04 玩樂
├── 404.html
├── style.css
├── assets/
│   ├── four-rooms.mp4    ASCII 動畫（20s, 1280x720）
│   ├── img/              headless browser 攞嘅網頁截圖
│   └── ascii/
│       └── four_rooms.py ASCII 動畫原始碼（頁面有 link 出去）
└── .github/workflows/
    └── deploy.yml        push 自動 build + deploy
```

## Deploy

```bash
git add -A && git commit -m "..." && git push
```

Actions 自動 deploy。驗證：

```bash
gh run list --workflow=deploy.yml --limit 1 --json databaseId,conclusion
curl -sI https://dorapwn.github.io/family-agent-site/ | head -1
```

唔好用 `gh run watch`（會被 runtime 當成 long-lived），poll `gh run list`。

## 常見改動

| 想改 | 改邊個檔 | 注意 |
|---|---|---|
| 指南內容 | `*.html` | 保持 `<a href="index.html">← 返主頁</a>` |
| 樣式 | `style.css` | 深色為主，手機優先 |
| ASCII 動畫 | `assets/ascii/four_rooms.py` → rerender | 每次 ~4 分鐘（4 核） |
| 新增指南頁 | 新 `*.html` + `index.html` 加卡 + deploy.yml 加檢查 | 三處都要改 |

## Rerender ASCII 動畫

```bash
cd assets/ascii
python four_rooms.py -o ../four-rooms.mp4 --workers 3
ffmpeg -y -ss 6.8 -i ../four-rooms.mp4 -frames:v 1 -q:v 3 ../img/poster.png
```

## 影網頁圖（截圖）

用 headless Chromium：

```bash
/opt/data/.toolchain/capture.sh <url> assets/img/<name>.png --full-page --wait-ms 4000
```

Captured directly from the source — no screenshot-of-a-screenshot.

---

*呢個網站由家庭助理自動生成。改 persona 記得同時改這邊，唔好兩邊脫節。*
*Persona 設定：`dorapwn/family-agent-guides`（private）*