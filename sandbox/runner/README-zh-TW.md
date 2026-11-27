# Self-hosted runner inside the sandbox VM

*English: [README.md](README.md)。兩份內容不一致時以英文版為準。*

補充產能與備援。Mac 開著時，VM 裡的 runner 會自動領取 conductor 排進 GitHub 的
`agent-job`，不需要人下指令。Ollama 的任務只能走這條路。

雲端 session 仍是主力，因為筆電闔上時它們照常運作。在 Mac 上，主要路徑是由本機 conductor 啟動的 Docker Sandbox（`sandbox/sbx.sh`）；這個 runner 位於 Lima 備援 VM 內，是兩者中較弱的一個。

這個 runner 還有第二個用途：當月 Actions 額度接近用完時，`agentctl budget` 會把 `ci` 與 `security` 這兩個執行 PR 程式碼的重型 job 改派到這裡。負責判定的 job 不會過來。

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

這份設定還沒在實機上跑過。完成後請執行 `docs/redteam-checklist.md`。
