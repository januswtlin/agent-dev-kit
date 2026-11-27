# Self-hosted runner inside the sandbox VM

補充產能與備援。Mac 開著時，VM 裡的 runner 會自動領取 conductor 排進 GitHub 的
`agent-job`，不需要人下指令。Ollama 的任務只能走這條路。

雲端 session 仍是主力，因為筆電闔上時它們照常運作。

## 安全前提

- Runner 裝在 VM 裡，不是裝在 macOS 上。VM 只掛載專案目錄，對外連線受 allowlist 限制。
- Runner 只服務這一個 private repo。不要把它註冊到 public repo：任何人開的 PR 都能在上面執行程式。
- VM 裡的 Claude Code 與 Codex 以你自己的訂閱登入；`auth.json` 與登入狀態視同密碼，只存在 VM 內。
- Workflow 用的 `AGENT_TOKEN` 是 machine user 的 fine-grained token，沒有 Workflows、Administration、Commit statuses 權限。

## 安裝

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh shell
```

以下在 VM 內執行。註冊用的 token 到 repo 的 Settings > Actions > Runners > New self-hosted runner 取得（Linux ARM64），依頁面指示下載並解壓到 `~/actions-runner`，然後：

```bash
cd ~/actions-runner && ./config.sh --url https://github.com/OWNER/REPO --token REGISTRATION_TOKEN --labels agent-sandbox --unattended
```

```bash
sudo ./svc.sh install && sudo ./svc.sh start
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

這份設定還沒在實機上跑過。完成後請執行 `docs/redteam-checklist.md`。
