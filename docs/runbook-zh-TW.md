# Runbook

*English: [runbook.md](runbook.md)。兩份內容不一致時以英文版為準。*

從零到無人看管運轉的步驟。依序做；每一段結尾有確認方式。
標示 **待驗證** 的地方是這份 template 還沒在真實帳號上跑過的部分，做的時候請對照當下的官方文件，並把結果回寫到這份文件。

## 0. 需要什麼

- GitHub organization，方案要能在 private repo 上強制 ruleset（Team 以上），每個人一個座位。Agent 與 conductor 都是 GitHub App，不佔座位。
- 每位名下會有 story 交給 agent 的人，至少一種 AI coding 訂閱，例如 Claude Max 或 ChatGPT。不需要 API key。
- 每個人的 Mac 上：Homebrew、`gh`、Lima（或 Docker Sandboxes）。

## 1. 建立專案 repo

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

## 2. 三種身分

### 2.1 Agent GitHub App（每位開發者一個）

每位開發者為自己的 agent 建立一個 GitHub App，這樣 commit 與留言就看得出是誰的 agent 做的。在你個人帳號的 Settings > Developer settings > GitHub Apps：

- 以自己命名，例如 `yourname-agent`。
- Repository permissions：Contents: Read and write；Pull requests: Read and write；Issues: Read and write；Metadata: Read。其他都不要，尤其**不要** Workflows、Administration、Commit statuses、Secrets、Variables。
- 不訂閱任何 webhook，取消勾選 Active。
- 建立後產生一把 private key，並把 App 只安裝到這個 repo。

留下 App 的 ID 與 private key 檔。第 5 節會把它們放進 VM。**待驗證**：`agentctl app-token` 還沒對真實 API 執行過。

要以留言啟動雲端任務，每位開發者另外需要一個個人 token `DISPATCH_TOKEN`：只限這個 repo 的 fine-grained personal access token，權限為 Issues: Read and write；Pull requests: Read and write；Metadata: Read。它出自開發者本人的帳號，因為留言者可能必須是連結了 ChatGPT 帳號的使用者（**待驗證**）。

### 2.2 Conductor GitHub App

在 organization 的 Settings > Developer settings > GitHub Apps 建立一個 App：

- Repository permissions：Contents: Read and write；Pull requests: Read and write；Issues: Read and write；Actions: Read and write；Variables: Read and write；Checks: Read；Commit statuses: Read；Metadata: Read。
- 不訂閱任何 webhook，取消勾選 Active。
- 建立後產生一把 private key，並把 App 安裝到這個 repo。

在 repo 的 Settings > Secrets and variables > Actions：

| 類型 | 名稱 | 值 |
|---|---|---|
| Variable | `CONDUCTOR_APP_ID` | App 的 ID |
| Secret | `CONDUCTOR_APP_PRIVATE_KEY` | private key 的完整內容 |

### 2.3 人類

專案裡的每個人都是 repo admin。Organization 的 Settings > Actions > General 中，確認 **Allow GitHub Actions to create and approve pull requests** 是關閉的。

## 3. Secrets 與 variables

| 類型 | 名稱 | 來源 | 何時需要 |
|---|---|---|---|
| Secret | `DISPATCH_TOKEN` | 2.1 | Codex 以留言啟動時 |
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` | 在你的機器上執行 `claude setup-token` | Claude review |
| Secret | `CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN` | 第 6 節建立的 scheduled task | Claude 雲端 session |
| Variable | `REVIEW_BOTS` | JSON 陣列，Codex review bot 的帳號，例如 `["chatgpt-codex-connector[bot]"]` **待驗證** | Codex review |
| Variable | `CONDUCTOR_PAUSED` | `true` 或留空 | Kill switch |
| Variable | `CONDUCTOR_QUOTA` | JSON，例如 `{"alice/codex": 1795800000}`，值為額度恢復的 epoch 秒 | 手動標記某個 harness 額度用盡 |
| Variable | `OLLAMA_MODEL` | 例如 `devstral` | 使用 Ollama 時 |
| Variable | `LIGHT_RUNNER` | 1-core runner 的 label **待驗證**；不設則用 `ubuntu-latest` | 想降低輕量 job 的費用時 |
| Variable | `CI_RUNNER` | 由 `agentctl budget` 自動維護，不需手動設定 | 額度 overflow |
| Variable | `CONDUCTOR_HOME`、`CONDUCTOR_LEASE`、`ACTIONS_USAGE` | 由 `agentctl` 自動維護 | Conductor 的位置與用量估算 |

屬於某個人訂閱的 secret（`DISPATCH_TOKEN`、`CLAUDE_CODE_OAUTH_TOKEN`、`CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN`）可以按開發者分開存放：在名稱後面加上大寫的帳號，其他字元換成 `_`，例如 `DISPATCH_TOKEN_ALICE`。Conductor 處理某位開發者的 story 時先找他專屬的 secret，找不到才用不帶後綴的名稱。只有一個人時，用不帶後綴的名稱就夠了。

## 4. Rulesets 與 repo 設定

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

## 5. Mac 與 sandbox

```bash
bin/agentctl doctor
```

修掉所有 FAIL。然後建立 VM：

```bash
brew install lima
```

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh check
```

進入 VM，登入你的 harness，並設定 agent 的 GitHub 身分：

```bash
sandbox/vm.sh shell
```

以下在 VM 內：

```bash
claude
```

```bash
codex login
```

```bash
mkdir -p ~/.config/agent-app && cat > ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

貼上你的 agent App 的 private key（第 2.1 節）後按 Ctrl-D。接著，把 `APP_ID` 換成你的 App ID、`yourname-agent` 換成你的 App 名稱：

```bash
echo 'export AGENT_APP_ID=APP_ID AGENT_APP_KEY=$HOME/.config/agent-app/key.pem PATH=/workspace/sandbox/bin:$PATH' >> ~/.profile && . ~/.profile
```

```bash
git config --global credential.https://github.com.helper '!/workspace/bin/agentctl app-token --git-credential' && git config --global user.name "yourname-agent[bot]" && git config --global user.email "yourname-agent[bot]@users.noreply.github.com"
```

之後 VM 內的 git 與 `gh` 都以你的 agent App 的身分操作。`sandbox/bin/gh` 包了一層 `gh`，每次呼叫都用新的一小時 token。Key 留在 VM 內：VM 若被入侵，外洩的是這個 App 對這一個 repo 的存取權（推 branch、留言、改 label），在 App 的設定頁刪除該 key 即可撤銷。

把 `codex/config.example.toml` 的 `vm` profile 複製到 VM 內的 `~/.codex/config.toml`。

把 story agent 專用的 deny rules 安裝為 VM 內的使用者層設定。這組規則禁止編輯 guardrail 路徑與已核准的 spec，只該對 story agent 生效，所以不放在 repo 共用的設定裡：

```bash
mkdir -p ~/.claude && cp /workspace/sandbox/story-agent.claude-settings.json ~/.claude/settings.json
```

雲端環境也要套用同一組規則（**待驗證**：兩家雲端服務設定使用者層規則的方式）。

若改用 Docker Sandboxes（隔離較嚴，建議）：**待驗證** 其指令。研究時查到的形式是 `sbx run claude`、`sbx run codex`，以及 `sbx policy allow network <domain>`。確認後把 `sandbox/allowlist.txt` 的主機逐一加入，並執行同一份 checklist。

Self-hosted runner 的安裝見 `sandbox/runner/README.md`。這是選配，建議在雲端路徑確認之後再決定要不要裝。

## 6. 雲端 agent

### Claude Code on the web

1. 在 claude.ai/code 以你自己的帳號連結 GitHub，只授權這個 repo。雲端 agent 之後在 GitHub 上是以你的身分操作。Red-team checklist 的 E 節檢查它用這個身分能做到什麼；讓雲端 session 無人看管地工作之前先跑過那一節。
2. 建立一個環境：網路設為受限，不加任何 secret。
3. 建立一個 scheduled task，觸發方式選 API，prompt 設為「執行收到的訊息中的指示」。把它的觸發 URL 與 token 存成 `CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN`。

**待驗證**：API trigger 的請求格式。`tools/agentctl/github.py` 的 `_send` 目前假設是帶 Bearer token 的 POST，body 為 `{"text": "..."}`。依實際文件調整這一個函式即可。

PO chat：在 Claude app 開一個掛著這個 repo 的 Claude Code session，輸入 `/po` 後說出需求。

### Codex cloud

1. 在 chatgpt.com/codex 連結 GitHub 並授權這個 repo。
2. 建立環境：agent 階段的網路關閉或設為 allowlist，不加 secret。
3. 開啟 automatic reviews。Review 規則讀 `AGENTS.md` 的 Code Review Rules 一節。

**待驗證**：在 PR 或 issue 上留 `@codex <指示>` 是否會啟動任意任務；review 的結果是以 PR review 還是留言呈現，`agent-review` workflow 的 `bridge` job 要對應調整。

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

執行 [redteam-checklist.md](redteam-checklist.md) 的全部項目。有任何一項成功就先修。

## 9. 第一個真正的 sprint

1. 在 `docs/product/roadmap.md` 加幾行需求，經 PR 合併；或用 PO chat 逐一討論。
2. 核准 PO 開的 spec PR。
3. Planner 會在 sprint 接近完成時起草下一個 sprint。第一個 sprint 需要手動請它起草：開一個 Claude Code session，要它依 `prompts/planner.md` 起草 sprint 001。
4. 核准 sprint PR。Conductor 從這裡接手。

### 開啟自動合併

維持 shadow mode 至少一個 sprint。每次 conductor 通知「可以合併」時，花一分鐘自己判斷一次，記下你是否同意。連續同意一段時間後，在 `policy/conductor.toml` 設：

```toml
auto_merge_tiers = ["T0"]
```

再過一段時間加上 `"T1"`。這個檔案的變更本身是 T2，需要你核准。

## 10. 新增一個人

1. 加入 organization，成為 repo admin。
2. 在 `policy/roles.toml` 把他加進 `humans`，並給他一個 `[developers.LOGIN.stages]` 區塊。在 `.github/CODEOWNERS` 把他加到他可以核准的路徑。只有在他要核准產品決定時，才加進 `directors` 與產品路徑。
3. 他建立自己的 agent App 與 `DISPATCH_TOKEN`（第 2.1 節），在自己的 Mac 上做第 5 節，並把自己的帳號連到雲端服務（第 6 節）。他的 secret 以他的帳號為後綴存放（第 3 節）。
4. 他名下的 story：在 story issue 上把 assignee 設為他，conductor 就會用他的 harness 設定、他的憑證與他的訂閱。
5. 產品決定仍只由 director 核准：`docs/specs/`、`docs/sprints/`、`docs/product/` 的 owner 只列 director。

## 11. 日常操作

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
| 懷疑有東西不對 | 暫停，然後跑一次 red-team checklist |

## 12. Ollama（之後再做）

Ollama 裝在 Mac 上（需要 GPU），VM 透過 host gateway 的 11434 port 存取，`sandbox/egress.sh` 已放行這個 port。

- 24GB 記憶體的 M2：選 14 到 15GB 級的模型（例如 devstral 24b、gpt-oss 20b）。19GB 級的模型加上大 context 會很吃緊。模型名稱與大小請以當下的 Ollama 模型庫為準。
- 一定要調高 context window。預設值很小，agent 會靜默遺失開頭的指示。
- 定位在 T0 類的工作：文件、lint 修正、測試骨架。產出一樣要過所有 gate。
- 在 `policy/roles.toml` 把想交給它的 stage 加上 `"ollama"`。它只能經 self-hosted runner 執行。
