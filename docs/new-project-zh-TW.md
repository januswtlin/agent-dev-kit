# 建立新專案

*English: [new-project.md](new-project.md)。兩份內容不一致時以英文版為準。*

每個專案做一次，由管理 GitHub organization 的人執行。做完之後，專案就可以讓人加入。

每個人之後在自己電腦上要做的事在 [new-machine-zh-TW.md](new-machine-zh-TW.md)。專案的日常運作在 [operations-zh-TW.md](operations-zh-TW.md)。

標示 **待驗證** 的地方還沒在真實的帳號或機器上跑過。做的時候請對照當下的官方文件，並把結果回寫到這份文件。

## 1. 需要什麼

- GitHub organization，方案要能在 private repo 上強制 ruleset（Team 以上），每個人一個座位。Agent 與 conductor 都是 GitHub App，不佔座位。

## 2. 建立專案 repo

在 GitHub 上以這個 repo 為 template，在 organization 下建立新的 private repo，然後 clone 到不受 iCloud 同步的位置：

```bash
mkdir -p ~/dev && cd ~/dev && gh repo clone OWNER/REPO
```

填入專案裡有誰。第一個帳號是 director，負責核准產品決定；列出的每個帳號都可以核准 T2 變更。只有一個人也可以：

```bash
scripts/init.sh DIRECTOR_LOGIN OTHER_LOGIN
```

接著打開 `policy/roles.toml`，為每個人設定哪個 harness 負責哪個 stage。檔案裡有單一廠商、兩家廠商、加上本地模型的範例。

確認：

```bash
make lint && make test
```

## 3. 專案的身分

專案本身有兩種身分：conductor，以及人。每個人的 agent 身分屬於他自己，在 [new-machine-zh-TW.md](new-machine-zh-TW.md) 設定。

### Conductor GitHub App

在 organization 的 Settings > Developer settings > GitHub Apps 建立一個 App：

- Repository permissions：Contents: Read and write；Pull requests: Read and write；Issues: Read and write；Actions: Read and write；Variables: Read and write；Checks: Read；Commit statuses: Read；Metadata: Read。
- 不訂閱任何 webhook，取消勾選 Active。
- 建立後產生一把 private key，並把 App 安裝到這個 repo。

在 repo 的 Settings > Secrets and variables > Actions：

| 類型 | 名稱 | 值 |
|---|---|---|
| Variable | `CONDUCTOR_APP_ID` | App 的 ID |
| Secret | `CONDUCTOR_APP_PRIVATE_KEY` | private key 的完整內容 |

### 人類

專案裡的每個人都是 repo admin。Organization 的 Settings > Actions > General 中，確認 **Allow GitHub Actions to create and approve pull requests** 是關閉的。

## 4. Secrets 與 variables

在 repo 的 Settings > Secrets and variables > Actions。這些屬於專案。屬於個人訂閱的 secret 在 [new-machine-zh-TW.md](new-machine-zh-TW.md) 第 3 節。

| 類型 | 名稱 | 來源 | 何時需要 |
|---|---|---|---|
| Variable | `REVIEW_BOTS` | JSON 陣列，Codex review bot 的帳號，例如 `["chatgpt-codex-connector[bot]"]` **待驗證** | Codex review |
| Variable | `CONDUCTOR_PAUSED` | `true` 或留空 | Kill switch |
| Variable | `CONDUCTOR_QUOTA` | JSON，例如 `{"alice/codex": 1795800000}`，值為額度恢復的 epoch 秒 | 手動標記某個 harness 額度用盡 |
| Variable | `OLLAMA_MODEL` | 例如 `devstral` | 使用 Ollama 時 |
| Variable | `LIGHT_RUNNER` | 1-core runner 的 label **待驗證**；不設則用 `ubuntu-latest` | 想降低輕量 job 的費用時 |
| Variable | `CI_RUNNER` | 由 `agentctl budget` 自動維護，不需手動設定 | 額度 overflow |
| Variable | `CONDUCTOR_HOME`、`CONDUCTOR_LEASE`、`ACTIONS_USAGE` | 由 `agentctl` 自動維護 | Conductor 的位置與用量估算 |

## 5. Rulesets 與 repo 設定

Template 的內容必須先在 `main` 上（required checks 對應的 workflow 要存在），再套用 ruleset。以 admin 身分執行：

```bash
scripts/apply-rulesets.sh
```

在 Settings > General > Pull Requests：開啟 Allow auto-merge、只允許 squash merging、開啟 Automatically delete head branches。

確認：

```bash
gh api repos/OWNER/REPO/rulesets --jq '.[].name'
```

應列出 `main` 與 `release-tags`。**待驗證**：`.github/rulesets/*.json` 的欄位是否被目前的 API 接受；若 API 回報未知欄位，依錯誤訊息調整後回寫。

## 6. 設定第一個人

做 spike 之前，至少要有一個人把 [new-machine-zh-TW.md](new-machine-zh-TW.md) 從頭到尾做完：他的 agent 身分、他的 sandbox、他的雲端帳號。

## 7. Spike：先證明一圈跑得完

在投入真正的 story 之前，用一個玩具 story 驗證整條路徑。目標是在不下任何手動指令的情況下，看到這個順序發生：

1. 建立 `docs/specs/001-hello/`（一個 AC、兩個 TC 的小功能）與 `docs/sprints/001.toml`（`stories = ["001"]`），經 PR 合併。
2. Conductor 執行，派發 `design`。先用 dry run 看它打算做什麼：

```bash
gh workflow run conductor.yml -f dry_run=true
```

3. Agent 推 `story/001-hello`，`open-pr` 以 draft 開 PR。Draft 只跑 lint 與 `risk-gate`。
4. 依序出現 `done:design`、`done:tests`、`done:impl`。`done:impl` 之後 conductor 把 PR 轉為可審，完整的 gate 第一次執行。
5. `agent-review` 被派發並寫入 status。
6. 五個 check 全綠。Shadow mode 下 conductor 通知你可以合併；你按 merge。
7. `evidence` 把對照表貼到 story issue。

Claude 與 Codex 各擔任一次實作。每一步若卡住，記下卡在哪裡與錯誤訊息：

| 卡住的地方 | 處理 |
|---|---|
| Conductor 讀狀態時出錯 | 修 `tools/agentctl/github.py` 的 `collect`。它還沒對真實 API 跑過 |
| 某個 harness 無法由雲端觸發 | 在 `policy/roles.toml` 把它改成 `via = "workflow"`，改用 self-hosted runner |
| Agent 沒有加 `done:*` label | 檢查 agent 身分是否有 Issues 寫入權；必要時在 prompt 中加強 |
| `agent-review` 一直 pending | 檢查 `CLAUDE_CODE_OAUTH_TOKEN`、`REVIEW_BOTS`，以及 action 的輸入參數 |
| PR 開了但 checks 沒跑 | PR 必須由 Conductor App 開啟，不是 `GITHUB_TOKEN` |

同時記下這些數字並回填 guideline 第 6 節的表：測試套件跑一次的分鐘數、一個 story 從開始到合併觸發了幾次完整的 gate、Actions 的 Usage 頁面顯示這個 story 用掉多少。

## 8. Red-team

執行 [redteam-project-zh-TW.md](redteam-project-zh-TW.md) 的全部項目。有任何一項成功就先修。

## 9. 第一個真正的 sprint

1. 在 `docs/product/roadmap.md` 加幾行需求，經 PR 合併；或用 PO chat 逐一討論。
2. 核准 PO 開的 spec PR。
3. Planner 會在 sprint 接近完成時起草下一個 sprint。第一個 sprint 需要手動請它起草：開一個 Claude Code session，要它依 `prompts/planner.md` 起草 sprint 001。
4. 核准 sprint PR。Conductor 從這裡接手。

自動合併一開始是關閉的。何時以及如何開啟，見 [operations-zh-TW.md](operations-zh-TW.md) 第 2 節。
