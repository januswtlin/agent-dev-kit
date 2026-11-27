# agent-dev-kit

*English: [README.md](README.md)。兩份內容不一致時以英文版為準。*

這是一份 guideline 加上一組工具，供 AI coding agent 在隔離環境中持續開發的專案使用，由人擔任 director。一個人或一個團隊都適用，Claude Code 與 Codex 可任意搭配（之後會加入 Ollama），只靠訂閱方案，不需要 API key。

兩個目標：

1. Agent 碰不到你的私人資料，也無法造成不可復原的損害。
2. 你不必閱讀一般的 pull request、不必 merge、也不必派工。你只做四件事：提出需求、核准 story、核准 sprint、發布到 production。

這個 kit 不是要複製進專案的範本。你在每台 Mac 上安裝某個版本一次，專案在 `agentdev.toml` 中以 commit SHA 固定（pin）該版本，專案的 workflow 以同一個 SHA 呼叫 kit 的 reusable workflow。kit 的程式碼完全不放在專案目錄樹中。

## 四個 layer

每個 layer 都可以單獨採用，並各有自己的設定文件與 checklist。

| Layer | 它提供什麼 | 設定與 checklist |
|---|---|---|
| 1. Isolation | Agent 在 clone 模式的 Docker Sandboxes (sbx) 中執行，或在廠商的雲端執行。每位開發者有自己的 GitHub App 給其 agent 使用。Mac 的安全習慣 | [docs/layer-1-isolation-zh-TW.md](docs/layer-1-isolation-zh-TW.md) |
| 2. GitHub protection | 預設 branch 與 release tag 的 ruleset、由你的設定產生的 CODEOWNERS、`conductor` environment、Conductor GitHub App | [docs/layer-2-github-zh-TW.md](docs/layer-2-github-zh-TW.md) |
| 3. CI gates | 五個 check：`ci`、`security`、`spec-verify`、`risk-gate` 與 `agent-review`，由 reusable workflow 執行，專案中很薄的 caller workflow 負責呼叫 | [docs/layer-3-ci-zh-TW.md](docs/layer-3-ci-zh-TW.md) |
| 4. Conductor | 在一台 Mac 上執行的程式，把 design、test、implementation 與 review 的 stage 派給 agent，並在你允許之後負責 merge | [docs/layer-4-conductor-zh-TW.md](docs/layer-4-conductor-zh-TW.md) |

對既有專案，先採用 layer 1 和 2，再採用 3，最後以 shadow mode（`auto_merge_tiers = []`）採用 4。順序與細節見 [docs/adopting-zh-TW.md](docs/adopting-zh-TW.md)。

## 運作方式

```
You say one sentence ─► PO agent writes a story ─► you approve
                                       │
              ┌────────────────────────┘
              ▼
        Conductor (a program with no state and no LLM, running on one Mac)
              │  dispatches work by the approved dependencies and priority
              ▼
   design ─► tests ─► impl ─► review        each stage is a brand-new agent session,
              │                              in a local sandbox or the vendor's cloud
              ▼
   all five required checks green ─► merge ─► evidence table posted to the issue
              │
              ▼
        you push a release tag ─► deploy
```

Agent 只能 push branch。其餘每一步都由 GitHub ruleset 與 check 把關。五個 check 中有四個是機械式的，不採信 agent 的任何說法，包括「你核准的每個 test case 都有一個真的會執行、而且會隨行為改變的測試」。

## 安裝

每台 Mac 一次，在這個 repository 的 clone 中執行：

```bash
./install.sh
```

這會把你目前 checkout 的版本，以完整 commit SHA 解開到 `~/.local/share/agent-dev-kit/versions/<sha>/`（唯讀），並把 `agentctl` launcher 放進 `~/.local/bin`。請把該目錄加入 `PATH`。多個版本可以並存。要安裝特定版本：

```bash
./install.sh <sha>
```

在專案中，launcher 執行 `agentdev.toml` 的 `[kit] version` 所固定的版本，該設定讀自專案的預設 branch（以最後一次 fetch 為準），絕不讀工作目錄。在專案之外，或在 pin 尚未進入預設 branch 的導入階段，請設定 `AGENTDEV_KIT_VERSION=<sha>`。

接著，在專案中：

```bash
agentctl init DIRECTOR_LOGIN
```

它會複製專案檔案而且不覆寫任何東西，並列出保留未動的檔案。在既有專案中執行之前，請先閱讀 [docs/adopting-zh-TW.md](docs/adopting-zh-TW.md)。

## 從哪裡開始閱讀

| 文件 | 內容 |
|---|---|
| [docs/guideline-zh-TW.md](docs/guideline-zh-TW.md) | 所有 layer 的設計與理由、哪些已驗證與哪些尚未驗證、已知限制。請先讀這份 |
| [docs/adopting-zh-TW.md](docs/adopting-zh-TW.md) | 在新專案或既有專案中使用 kit：install、init、layer 的順序、升級、移除 |
| [docs/layer-1-isolation-zh-TW.md](docs/layer-1-isolation-zh-TW.md) 到 [docs/layer-4-conductor-zh-TW.md](docs/layer-4-conductor-zh-TW.md) | 每個 layer 一份設定指南與 checklist |
| [docs/threat-model-zh-TW.md](docs/threat-model-zh-TW.md) | 威脅，以及對應的控制措施 |
| [examples/](examples/) | 一句需求變成一個 story 的範例，以及一份 sprint 檔案 |
| [AGENTS.md](AGENTS.md) | 維護 kit 本身的 agent 所遵守的規則。專案中 agent 的規則在 `templates/project/AGENTS.md` |

## 指令

`agentctl --help` 會列出全部指令。你會用到的指令：

| 指令 | 作用 |
|---|---|
| `agentctl init DIRECTOR [HUMAN ...]` | 把專案檔案複製進專案，絕不覆寫。`--dry-run` 會列出它將要做的事 |
| `agentctl doctor` | 檢查 Mac 的主機安全習慣。`--inside` 從 sandbox 內部檢查邊界 |
| `agentctl sandbox setup` | 每台 Mac、每個專案一次：鎖定 sbx 並安裝 token helper |
| `agentctl rulesets 2 [OWNER/REPO]` | 建立或更新 layer 2 的 ruleset：`main`、`main-merge`、`tags`（由 admin 執行，並設定 `CONDUCTOR_APP_ID`） |
| `agentctl rulesets 3 [OWNER/REPO]` | 建立或更新 `main-checks`，也就是必要的 check。必須等 layer 3 的 caller 已進入預設 branch 之後才能套用 |
| `agentctl codeowners [--check]` | 印出由 `agentdev.toml` 產生的 `.github/CODEOWNERS`，或檢查已 commit 的那一份 |
| `agentctl conductor` | 在這個終端機中執行 conductor。`--dry-run` 印出一次 pass 的計畫而不採取任何行動。Ctrl-C 停止它 |
| `agentctl config KEY` | 印出一項設定，例如 `tests.test_cmd` |
| `agentctl pins` | 檢查 caller workflow 使用的 kit 版本是否為 `agentdev.toml` 所固定的版本 |
| `agentctl prompt STAGE` | 印出某個 stage 的 prompt，已填入這個專案的設定 |
| `agentctl status` | director's brief 所用的 sprint 摘要 |
| `agentctl budget` | 估算本月的 Actions 花費 |

其餘指令（`risk`、`spec-lint`、`docs-lint`、`trace`、`redgreen`、`redgreen-collect`、`redgreen-judge`、`evidence`、`collect-junit`、`app-token`、`stage-profile`、`harness-settings`、`story-of`、`repo-name`、`junit-unittest`）由 workflow 與 sandbox 腳本執行。

要檢查 kit 本身（在 clone 中）：

```bash
make lint
```

```bash
make test
```

## 狀態

這些工具有單元測試，而且都通過。Red-green 已在真實的 git repository 上端到端執行過。**尚未有任何部分在真實的 GitHub、Docker Sandboxes、廠商的雲端服務或 Mac 上執行過。** 已驗證與尚未驗證的清單在 [guideline](docs/guideline-zh-TW.md)（第 11 節）中，每個 layer 的文件結尾也有可以確認該 layer 的 check。在某個 layer 的 checklist 完成之前，不要倚賴該 layer，也不要讓 conductor 無人看管地執行。

整個 kit 的已知限制在 [guideline](docs/guideline-zh-TW.md)（第 12 節）中。

## 語言

文件以英文檔為主。繁體中文版放在同一個目錄中，檔名以 `-zh-TW` 結尾。Story 的做法相同：`story.md` 是 agent 據以實作的版本，`story-zh-TW.md` 是 director 閱讀並核准的版本。專案可以在 `agentdev.toml` 以 `[stories] translation` 選擇其他語言，或不使用。
