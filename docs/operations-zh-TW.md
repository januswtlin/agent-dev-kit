# 日常運作

*English: [operations.md](operations.md)。兩份內容不一致時以英文版為準。*

專案設定完成之後的運作。設定步驟在 [new-project-zh-TW.md](new-project-zh-TW.md) 與 [new-machine-zh-TW.md](new-machine-zh-TW.md)。

## 1. 日常操作

Conductor 在哪裡跑由你決定。在電腦前時讓它跑在 terminal，不耗 Actions 額度，反應也快：

```bash
bin/agentctl conductor here
```

外出前按 Ctrl-C，或在另一個 terminal 執行：

```bash
bin/agentctl conductor away
```

忘了交接也沒關係，lease 20 分鐘沒更新，Actions 的排程執行會自動接手。查看目前在哪裡：

```bash
bin/agentctl conductor status
```

本機執行需要派工用的觸發網址與 token。在專案根目錄建立 `.env.conductor`（已列入 `.gitignore`），內容是 `CLAUDE_TRIGGER_URL=...`、`CLAUDE_TRIGGER_TOKEN=...` 這樣的行。

| 情況 | 做法 |
|---|---|
| 想暫停一切 | 把 variable `CONDUCTOR_PAUSED` 設為 `true` |
| 想知道現在的狀態 | 看 Director's brief issue，或執行 `bin/agentctl status --markdown` |
| 想知道 conductor 接下來會做什麼 | `gh workflow run conductor.yml -f dry_run=true`，看執行紀錄 |
| 某個 story 被標 `needs-human` | 讀 issue 上 triage 的說明與選項，決定後移除 label；需要改 spec 就改 spec |
| 某個 harness 額度用盡 | 設 `CONDUCTOR_QUOTA`，到期後 conductor 會自動恢復使用 |
| 想讓某個 story 暫時不做 | 在它的 issue 加上 `blocked` label |
| 要上線 | 在 main 上你要的 commit 打 `v*` tag 並 push |
| 想知道 Actions 用了多少 | `bin/agentctl budget --dry-run`，或看 brief 的第一行 |
| 要修改 pipeline 本身 | 在 session 裡直接要求 agent，在 `chore/` branch 上進行，PR 由你核准 |
| 懷疑有東西不對 | 暫停，然後跑一次 [redteam-project-zh-TW.md](redteam-project-zh-TW.md) 與 [redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) |

## 2. 開啟自動合併

維持 shadow mode 至少一個 sprint。每次 conductor 通知「可以合併」時，花一分鐘自己判斷一次，記下你是否同意。連續同意一段時間後，在 `policy/conductor.toml` 設：

```toml
auto_merge_tiers = ["T0"]
```

再過一段時間加上 `"T1"`。這個檔案的變更本身是 T2，需要你核准。

## 3. 新增一個人

1. 加入 organization，成為 repo admin。
2. 在 `policy/roles.toml` 把他加進 `humans`，並給他一個 `[developers.LOGIN.stages]` 區塊。在 `.github/CODEOWNERS` 把他加到他可以核准的路徑。只有在他要核准產品決定時，才加進 `directors` 與產品路徑。
3. 他把 [new-machine-zh-TW.md](new-machine-zh-TW.md) 從頭到尾做完：自己的 agent App、自己的 secret（以他的帳號為後綴存放）、他的 sandbox、他自己的雲端帳號。
4. 他名下的 story：在 story issue 上把 assignee 設為他，conductor 就會用他的 harness 設定、他的憑證與他的訂閱。
5. 產品決定仍只由 director 核准：`docs/specs/`、`docs/sprints/`、`docs/product/` 的 owner 只列 director。
