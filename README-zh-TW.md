# agent-dev-template

*English: [README.md](README.md)。兩份內容不一致時以英文版為準。*

讓 AI coding agent 在隔離環境中持續開發、由人類擔任 director 的專案 template。
一個人或一個團隊都適用，可任意混用 Claude Code 與 Codex（之後加上 Ollama），只用訂閱，不需要 API key。

兩個目標：

1. Agent 碰不到你的私人資料，也造不成不可挽回的破壞。
2. 你不讀一般的 PR、不 merge、不派工。你只做四件事：說出需求、核准 story、核准 sprint、放行上線。

## 怎麼運作

```
你說一句話 ─► PO agent 寫成 story ─► 你核准
                                       │
              ┌────────────────────────┘
              ▼
        Conductor（無狀態的排程程式，跑在你的 terminal 或 GitHub Actions）
              │  依核准的相依關係與優先序派工
              ▼
   design ─► tests ─► impl ─► review        每個 stage 是全新的 agent session，
              │                              在 VM 或廠商的雲端執行
              ▼
   五個 required checks 全綠 ─► 合併 ─► 對照表貼回 issue
              │
              ▼
        你打 release tag ─► 部署
```

Agent 只能推 branch。其餘的每一步都由 GitHub 的 ruleset 與檢查把關，其中四項是不採信 agent 說法的機械檢查，包括「每個你核准的 test case 都有一個真的在跑、而且會隨行為改變的測試」。

## 從哪裡開始讀

| 文件 | 內容 |
|---|---|
| [docs/guideline-zh-TW.md](docs/guideline-zh-TW.md) | 設計與理由。先讀這份 |
| [docs/new-project-zh-TW.md](docs/new-project-zh-TW.md) | 每個專案做一次：repo、conductor、rulesets、spike |
| [docs/new-machine-zh-TW.md](docs/new-machine-zh-TW.md) | 每個人、每台電腦做一次：agent 身分、sandbox、雲端帳號 |
| [docs/operations-zh-TW.md](docs/operations-zh-TW.md) | 日常：conductor 在哪裡跑、自動合併、新增一個人 |
| [docs/threat-model-zh-TW.md](docs/threat-model-zh-TW.md) | 威脅與對應的控制 |
| [docs/redteam-project-zh-TW.md](docs/redteam-project-zh-TW.md)、[docs/redteam-machine-zh-TW.md](docs/redteam-machine-zh-TW.md) | 驗證防線真的有效的測試清單，專案一份、每台電腦一份 |
| [docs/specs/000-example/](docs/specs/000-example/) | 一句需求變成 story 的範例 |
| [AGENTS.md](AGENTS.md) | 所有 agent 遵守的規則 |

## 目錄

| 路徑 | 用途 |
|---|---|
| `tools/agentctl/` | 風險分級、spec 與文件檢查、traceability、red-green、conductor、Actions 額度估算。Python 標準函式庫，無相依 |
| `policy/` | 風險規則、conductor 上限、角色分配、與技術棧的契約 |
| `prompts/` | 各 stage 的指令，與廠商無關 |
| `.github/` | Workflows、rulesets、CODEOWNERS |
| `sandbox/` | Docker Sandboxes 的設定（clone 模式）、egress allowlist、Lima 備援。其中的 self-hosted runner 不屬於受支援的設定 |
| `.claude/`、`codex/` | 各 harness 的設定 |
| `docs/specs/`、`docs/sprints/`、`docs/product/` | 你核准的東西 |

## 狀態

工具層有單元測試並通過；red-green 在真實的 git repo 上端對端驗證過。
與真實 GitHub API、兩家雲端服務、macOS sandbox 的整合還沒在實機上跑過，
清單在 [guideline 第 9 節](docs/guideline-zh-TW.md#9-已驗證與未驗證)，驗證步驟在 [docs/new-project-zh-TW.md](docs/new-project-zh-TW.md) 的 spike 一節。
在完成 spike 與兩份 red-team checklist 之前，不要讓它無人看管地運轉。

## 語言

文件以英文為主檔，繁體中文在同目錄以 `-zh-TW` 結尾的檔名並列。Story 也是：`story.md` 是 agent 實作的依據，`story-zh-TW.md` 是 director 閱讀與核准的版本。

## 指令

```bash
make lint
```

```bash
make test
```

```bash
bin/agentctl --help
```

```bash
bin/agentctl conductor here
```
