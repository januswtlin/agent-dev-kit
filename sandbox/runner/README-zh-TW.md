# Self-hosted runner inside the sandbox VM

*English: [README.md](README.md)。兩份內容不一致時以英文版為準。*

**這條路徑不屬於受支援的設定。** 設定專案或機器時不要照這一頁做。保留這一頁，是給想把這件事做完的人當參考。受支援的本機路徑是由本機 conductor 啟動的 Docker Sandbox（`sandbox/sbx.sh`），見 [docs/new-machine-zh-TW.md](../../docs/new-machine-zh-TW.md)。

不受支援的原因：

- Lima VM 長期存在、有免密碼的 sudo，還保存著 agent 的登入狀態（Claude Code、Codex、agent App 的 key）。在它的 runner 上執行的程式碼可以改動防火牆、讀取這些登入狀態，並且留下來影響之後的 job。Runner 在 job 之間不會重建。
- 因此預算 overflow **預設是關閉的**：`policy/conductor.toml` 的 `overflow_runner = []`。`agentctl budget` 仍然會估算並回報用量，但在沒有設定 runner 時不會搬動任何東西。`ci` 與 `security` 會執行 pull request 的程式碼。它們只能移到專門給它們用、不保存任何憑證或登入狀態、而且每個 job 都重建的 runner。這個 VM 不符合條件，這個 template 也沒有提供這樣的 runner。沒有 overflow 時，Actions 額度一用完，CI 就會停止，在下個月或你加購額度之前不會有任何東西被合併。

如果你仍然要設定它，已知的缺口如下：

- `sandbox/allowlist.txt` 與 `sandbox/allowlist-build.txt` 沒有列出 GitHub Actions runner 需要的主機，所以以目前的設定，runner 在 VM 的 egress 過濾之下無法運作（**待驗證**：主機清單，以 GitHub 的 self-hosted runner 文件為準）。
- Runner 的 service 拿不到 `AGENT_APP_ID` 與 `AGENT_APP_KEY`。[docs/new-machine-zh-TW.md](../../docs/new-machine-zh-TW.md) 把它們 export 在 `~/.profile`，只有 login shell 會讀這個檔案。`agent-job` workflow 會呼叫 `bin/agentctl app-token`，它需要這兩個變數。
- 這裡的內容都還沒在實機上跑過。

它原本的設計用途：Mac 開著時，VM 裡的 runner 會領取 conductor 排進 GitHub 的
`agent-job`，對象是在 `policy/roles.toml` 設為 `via = "workflow"` 的 harness。預設沒有任何 harness 使用這個設定。

Ollama 的 stage **不**在這裡執行。它們在本機的 Docker Sandbox 內執行，由本機 conductor 啟動（`via = "sbx"`）。

雲端 session 仍是主力，因為筆電闔上時它們照常運作。在 Mac 上，主要路徑是由本機 conductor 啟動的 Docker Sandbox（`sandbox/sbx.sh`）；這個 runner 位於 Lima 備援 VM 內，是兩者中較弱的一個。

這個 runner 原本還要在當月 Actions 額度接近用完時接手 `ci` 與 `security`。那就是上面說的 overflow，目前是關閉的。負責判定 pull request 的 job 永遠不會移到 self-hosted runner。

## 安全前提

- Runner 裝在 VM 裡，不是裝在 macOS 上。VM 只掛載專案目錄，對外連線受 allowlist 限制。
- Runner 只服務這一個 private repo。不要把它註冊到 public repo：任何人開的 PR 都能在上面執行程式。
- VM 裡的 Claude Code 與 Codex 以你自己的訂閱登入；`auth.json` 與登入狀態視同密碼，只存在 VM 內。
- Runner 在 GitHub 上以你自己的 agent GitHub App 的身分操作，它沒有 Workflows、Administration、Commit statuses 權限。註冊 runner 時把你的 GitHub 帳號加為 label，你名下的 story 才會在你的機器、用你的訂閱執行。

## 安裝

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh shell
```

以下在 VM 內執行。註冊用的 token 到 repo 的 Settings > Actions > Runners > New self-hosted runner 取得（Linux ARM64），依頁面指示下載並解壓到 `~/actions-runner`，然後：

```bash
cd ~/actions-runner && ./config.sh --url https://github.com/OWNER/REPO --token REGISTRATION_TOKEN --labels agent-sandbox,YOUR_LOGIN --unattended
```

```bash
sudo ./svc.sh install && sudo ./svc.sh start
```

安裝 story agent 專用的 deny rules（禁止編輯 guardrail 路徑與已核准的 spec）：

```bash
mkdir -p ~/.claude && cp /workspace/sandbox/story-agent.claude-settings.json ~/.claude/settings.json
```

在 VM 內登入兩個 harness（各做一次）：

```bash
claude
```

```bash
codex login
```

## 讓 VM 隨 Mac 登入自動啟動

把 `com.agent-sandbox.vm.plist` 複製到 `~/Library/LaunchAgents/`，將其中的
`PROJECT_DIR` 換成專案的絕對路徑，然後：

```bash
launchctl load ~/Library/LaunchAgents/com.agent-sandbox.vm.plist
```

MacBook Air 闔上螢幕就會睡眠，睡眠期間 runner 離線，排隊中的工作會等到喚醒後才執行。
這是把雲端當主力的原因。

## 尚未驗證

這份設定還沒在實機上跑過，也不屬於受支援的設定（見本頁開頭）。如果你仍然把它裝起來，請執行 `docs/redteam-machine-zh-TW.md`。
