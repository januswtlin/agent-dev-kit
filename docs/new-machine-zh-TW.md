# 設定一個人與他的電腦

*English: [new-machine.md](new-machine.md)。兩份內容不一致時以英文版為準。*

每位名下會有 story 交給 agent 的人各自執行。第 2、3、5 節是每個人在每個專案做一次；第 4 節是每台電腦做一次，換新電腦時重做。前提是專案已經建立（[new-project-zh-TW.md](new-project-zh-TW.md)）。

標示 **待驗證** 的地方還沒在真實的帳號或機器上跑過。做的時候請對照當下的官方文件，並把結果回寫到這份文件。

## 1. 需要什麼

- 每位名下會有 story 交給 agent 的人，至少一種 AI coding 訂閱，例如 Claude Max 或 ChatGPT。不需要 API key。
- Mac 上：`gh` 與 Docker Sandboxes（`sbx`）。只有使用備援 VM 時才需要 Homebrew 與 Lima。

## 2. Agent GitHub App

每位開發者為自己的 agent 建立一個 GitHub App，這樣 commit 與留言就看得出是誰的 agent 做的。在你個人帳號的 Settings > Developer settings > GitHub Apps：

- 以自己命名，例如 `yourname-agent`。
- Repository permissions：Contents: Read and write；Pull requests: Read and write；Issues: Read and write；Metadata: Read。其他都不要，尤其**不要** Workflows、Administration、Commit statuses、Secrets、Variables。
- 不訂閱任何 webhook，取消勾選 Active。
- 建立後產生一把 private key，並把 App 只安裝到這個 repo。

留下 App 的 ID 與 private key 檔。第 4 節會把它們放在你的 Mac 上、sandbox 之外。**待驗證**：`agentctl app-token` 還沒對真實 API 執行過。

要以留言啟動雲端任務，每位開發者另外需要一個個人 token `DISPATCH_TOKEN`：只限這個 repo 的 fine-grained personal access token，權限為 Issues: Read and write；Pull requests: Read and write；Metadata: Read。它出自開發者本人的帳號，因為留言者可能必須是連結了 ChatGPT 帳號的使用者（**待驗證**）。

## 3. 你的 secrets

在 repo 的 Settings > Secrets and variables > Actions。這些屬於你自己的訂閱。

| 類型 | 名稱 | 來源 | 何時需要 |
|---|---|---|---|
| Secret | `DISPATCH_TOKEN` | 第 2 節 | Codex 以留言啟動時 |
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` | 在你的機器上執行 `claude setup-token` | Claude review |
| Secret | `CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN` | 第 5 節建立的 scheduled task | Claude 雲端 session |

屬於某個人訂閱的 secret（`DISPATCH_TOKEN`、`CLAUDE_CODE_OAUTH_TOKEN`、`CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN`）可以按開發者分開存放：在名稱後面加上大寫的帳號，其他字元換成 `_`，例如 `DISPATCH_TOKEN_ALICE`。Conductor 處理某位開發者的 story 時先找他專屬的 secret，找不到才用不帶後綴的名稱。只有一個人時，用不帶後綴的名稱就夠了。

## 4. Mac 與 sandbox

```bash
bin/agentctl doctor
```

修掉所有 FAIL。本機 sandbox 用的是 clone 模式的 Docker Sandboxes。依其文件安裝 `sbx`（docs.docker.com/ai/sandboxes），然後登入：

```bash
sbx login
```

把你的 agent App 的 ID 與 private key（第 2 節）放在 Mac 上。它們留在 host，sandbox 內的任何東西都讀不到。把 `APP_ID` 換成你的 App ID，檔名換成你下載的 key 檔：

```bash
mkdir -p ~/.config/agent-app && echo APP_ID > ~/.config/agent-app/app-id
```

```bash
mv ~/Downloads/YOUR_APP.private-key.pem ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

接著：

```bash
sandbox/sbx.sh setup
```

這會關掉 sbx 的 SSH agent forwarding（這個設定對你所有的 sandbox 生效）、放行 `sandbox/allowlist.txt` 所列的主機，並把 token helper 安裝在 repo 之外，內容取自 default branch 上的工具。若要讓 sandbox 能連到 Mac 上的 Ollama，改用 `AGENT_OLLAMA=1 sandbox/sbx.sh setup` 執行。

依 sbx 文件對各 harness 的說明登入。撰寫本文時，Codex 是在 host 上執行 `sbx secret set openai --oauth`，Claude Code 是在 sandbox 內執行 `/login`（**待驗證**）。

啟動一個互動式的 agent，然後在第二個 terminal 檢查邊界。可以加第二個參數指定 stage，sandbox 就拿到該 stage 的權限，例如 `sandbox/sbx.sh up claude review` 會拿到不能 push 的 token；預設是 `impl`。拉下工具的更新之後，要再執行一次 `sandbox/sbx.sh setup` 來更新固定的副本：

```bash
sandbox/sbx.sh up claude
```

```bash
sandbox/sbx.sh check
```

Agent 在自己的 clone 上工作，以 push 交付成果。想在它 push 之前看它的工作，可以從 sbx 加到你 repo 的 remote 取得（`REPO` 是目錄名稱）：

```bash
git fetch sandbox-agent-REPO-claude
```

**待驗證**（實機）：這一節的全部內容。特別要確認 sandbox 內的 `git push` 會成功，而且歸屬於你的 agent App，並把結果記在 [redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) 的 C11。

備援：Lima。在你無法使用 sbx 時，或是要跑 self-hosted runner（`sandbox/runner/README-zh-TW.md`）時使用。它較弱：workspace 是可讀寫掛載、連線以位址過濾、App 的 key 必須放在 VM 內。

```bash
brew install lima
```

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh check
```

```bash
sandbox/vm.sh shell
```

以下在 VM 內執行。先登入你的 harness（`claude`、`codex login`），再把 agent App 的 key 交給 VM：

```bash
mkdir -p ~/.config/agent-app && cat > ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

貼上 private key 後按 Ctrl-D。接著，把 `APP_ID` 換成你的 App ID、`yourname-agent` 換成你的 App 名稱：

```bash
echo 'export AGENT_APP_ID=APP_ID AGENT_APP_KEY=$HOME/.config/agent-app/key.pem PATH=/workspace/sandbox/bin:$PATH' >> ~/.profile && . ~/.profile
```

```bash
git config --global credential.https://github.com.helper '!/workspace/bin/agentctl app-token --git-credential' && git config --global user.name "yourname-agent[bot]" && git config --global user.email "yourname-agent[bot]@users.noreply.github.com"
```

```bash
mkdir -p ~/.claude && cp /workspace/sandbox/story-agent.claude-settings.json ~/.claude/settings.json
```

最後一個指令安裝的是 story agent 專用的 deny rules。另外把 `codex/config.example.toml` 的 `vm` profile 複製到 `~/.codex/config.toml`。雲端環境也要套用同一組 story agent 規則（**待驗證**：兩家雲端服務設定使用者層規則的方式）。

## 5. 雲端 agent

### Claude Code on the web

1. 在 claude.ai/code 以你自己的帳號連結 GitHub，只授權這個 repo。雲端 agent 之後在 GitHub 上是以你的身分操作。[redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) 的 E 節檢查它用這個身分能做到什麼；讓雲端 session 無人看管地工作之前先跑過那一節。
2. 建立一個環境：網路設為受限，不加任何 secret。
3. 建立一個 scheduled task，觸發方式選 API，prompt 設為「執行收到的訊息中的指示」。把它的觸發 URL 與 token 存成 `CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN`。

**待驗證**：API trigger 的請求格式。`tools/agentctl/github.py` 的 `_send` 目前假設是帶 Bearer token 的 POST，body 為 `{"text": "..."}`。依實際文件調整這一個函式即可。

PO chat：在 Claude app 開一個掛著這個 repo 的 Claude Code session，輸入 `/po` 後說出需求。

### Codex cloud

1. 在 chatgpt.com/codex 連結 GitHub 並授權這個 repo。
2. 建立環境：agent 階段的網路關閉或設為 allowlist，不加 secret。
3. 開啟 automatic reviews。Review 規則讀 `AGENTS.md` 的 Code Review Rules 一節。

**待驗證**：在 PR 或 issue 上留 `@codex <指示>` 是否會啟動任意任務；review 的結果是以 PR review 還是留言呈現，`agent-review` workflow 的 `bridge` job 要對應調整。

## 6. Red-team

在這台電腦上執行 [redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) 的全部項目。有任何一項成功，就先修好再讓 agent 無人看管地工作。

## 7. Ollama（之後再做）

Ollama 裝在 Mac 上（需要 GPU）。以 `AGENT_OLLAMA=1 sandbox/sbx.sh setup` 放行該 port 之後，sandbox 可經 `host.docker.internal:11434` 存取它。在 Lima 備援中，`sandbox/egress.sh` 已經透過 host gateway 放行。

- 24GB 記憶體的 M2：選 14 到 15GB 級的模型（例如 devstral 24b、gpt-oss 20b）。19GB 級的模型加上大 context 會很吃緊。模型名稱與大小請以當下的 Ollama 模型庫為準。
- 一定要調高 context window。預設值很小，agent 會靜默遺失開頭的指示。
- 定位在 T0 類的工作：文件、lint 修正、測試骨架。產出一樣要過所有 gate。
- 在 `policy/roles.toml` 把想交給它的 stage 加上 `"ollama"`。它在本機 sandbox 內執行，所以這些 stage 只有在 conductor 跑在你的 Mac 上（`agentctl conductor here`）時才會開始。
