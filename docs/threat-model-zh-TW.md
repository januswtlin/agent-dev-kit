# Threat model

*English: [threat-model.md](threat-model.md)。兩份內容不一致時以英文版為準。*

每一列是一類實際發生過或可預期的事故，對應到擋住它的控制。控制分兩種：**硬性**的由環境或 GitHub 強制，agent 無法繞過；**軟性**的可以被繞過，只當第二層。

## 資產

| 資產 | 最壞情況 | 可復原嗎 |
|---|---|---|
| Mac 上的私人資料 | 被讀取並進入廠商的 context，或被送到外部 | 否 |
| Mac 上工作目錄以外的檔案 | 被刪除或覆寫 | 靠備份 |
| 暫時有效的雲端 CLI token | 在有效期間被用來操作雲端資源 | 視操作而定 |
| Repo 的歷史與 main | 被改寫，或被合入有問題的程式 | 是（git），但代價高 |
| 護欄本身（workflow、policy、spec） | 被削弱後，其他防線失效 | 是，前提是有人發現 |
| 訂閱帳號的登入狀態 | 被竊取 | 可撤銷 |
| 未來的 production 與資料庫 | 被刪除或外洩 | 否 |

## 威脅與控制

| # | 威脅 | 硬性控制 | 軟性控制 |
|---|---|---|---|
| 1 | Agent 讀取 home 下的私人檔案 | VM 只掛載 worktree；雲端 session 不在你的機器上 | `.claude/settings.json` 的 `denyRead`；guard hook |
| 2 | Agent 誤刪工作目錄以外的檔案（`rm -rf ~/`） | 同上：VM 內沒有那些檔案 | guard hook；專案不放在 iCloud 同步的目錄；備份 |
| 3 | Agent 使用機器上的雲端憑證 | VM 內沒有 `~/.aws` 等目錄 | deny rules 擋雲端 CLI |
| 4 | Prompt injection（repo 內容、issue、網頁、套件說明）誘使 agent 外送資料 | Egress allowlist；VM 內沒有值得外送的秘密，除了訂閱登入狀態與 agent token | AGENTS.md 第 7 條 |
| 5 | Agent 安裝惡意或不存在的套件（slopsquatting、被入侵的套件） | 依賴變更一律 T2，需人類核准才能合併；安裝發生在 VM 內；egress allowlist 限制回連 | AGENTS.md 第 5 條 |
| 6 | Agent 直接 push main、force push、刪 branch | Ruleset：main 只能經 PR；agent 是 Write 權限的 machine user，沒有 bypass | guard hook；deny rules |
| 7 | Agent 修改 CI 讓檢查通過 | Agent token 沒有 Workflows 權限；`.github/` 在 CODEOWNERS；檢查使用 base branch 的工具與 policy | AGENTS.md 第 3 條 |
| 8 | Agent 削弱風險規則、prompt 或工具 | `policy/`、`prompts/`、`tools/` 在 CODEOWNERS，且為 T2 | 同上 |
| 9 | Agent 聲稱寫了測試但沒有，或寫了空測試 | `spec-verify`：traceability（依執行結果）與 red-green | 審查 agent 的忠實度稽核 |
| 10 | Agent 修改或刪除測試來遷就實作 | Spec 受 CODEOWNERS 保護；已通過的 TC 不得消失；red-green | 審查 agent 逐一檢查測試階段之後的測試變更 |
| 11 | Agent 悄悄更改需求 | `docs/specs/` 在 CODEOWNERS；新的 push 使舊核准失效 | |
| 12 | Agent 核准或合併自己的 PR | Agent 帳號不是 code owner；PR 由 Conductor App 開啟；App 不能核准 | deny rules 擋 `gh pr merge` |
| 13 | Agent 偽造 `agent-review` 的結果 | Agent token 沒有 commit status 權限；Claude review 由 workflow job 寫入 | 見 guideline 4 的說明：這是最弱的一環，硬性保證不依賴它 |
| 14 | Agent 自行部署或建立 release | Tag ruleset：`v*` 只有 admin 能建；雲端只信任來自 tag 的 OIDC；沒有長期金鑰 | |
| 15 | Agent 刪除 production 資料庫或備份 | Agent 與 CI 沒有 production 憑證；部署角色沒有刪除備份的權限；migration 為 T2 | |
| 16 | Secret 被 commit | `security` check 的 gitleaks | AGENTS.md 第 6 條 |
| 17 | Conductor 失控：無限重試、大量開 PR | 每日 PR 上限、重試與 fix 輪數上限、WIP 上限、kill switch | 每日 brief |
| 18 | 長時間運作後 agent 偏離指示 | 沒有長 session：每個 stage 是全新 context，狀態在 GitHub | |
| 19 | 模型升級後行為改變 | 排程是決定性程式；gate 是機械檢查 | 每週稽核抽樣 |
| 20 | Computer use、瀏覽器擴充、個人資料 connector 碰到私人資料 | 無。這些路徑不經過 VM | 規則：不開啟。見 guideline 3 |
| 21 | Agent 直接寫出假的測試結果檔，騙過 `spec-verify` | 無。測試結果本來就由 PR 的程式碼產生 | `Makefile` 受 CODEOWNERS 保護；審查 agent；每週抽查 |
| 22 | 雙語 story 的兩份語意不同：你核准的中文與 agent 實作的英文有出入 | 結構一致與同步變更由 `spec-lint` 強制 | PO 自我比對；另一廠商的 review agent 逐條比對 |
| 23 | PR 的程式碼在 self-hosted runner 上留下東西，影響之後的 job | 負責判定的 job 永遠在 GitHub-hosted runner 上；溢出的只有 `ci` 與 `security` | Runner 在 VM 內 |
| 24 | 維護用的 session 被誘導去削弱護欄 | 護欄路徑的變更一律需要人類核准才能合併 | AGENTS.md 第 3 條：只有人類在 session 中直接提出才算維護要求 |
| 25 | Actions 額度被耗盡，gate 無法執行 | 額度用完時 PR 無法合併，不會在沒有 gate 的情況下合併 | 用量估算、溢出到 self-hosted、每日 brief |

## 參考事故

設計時參考的公開事故類型，用來檢查上表是否有遺漏：

- Agent 在被明確要求停止變更的情況下刪除 production 資料庫（2025 年 7 月，Replit 與 SaaStr）。對應 #14、#15。
- Agent 透過雲端平台的 API 刪除資料庫與備份（2026 年 4 月的報導）。對應 #3、#15。
- 被入侵的 npm 套件指示本機的 AI CLI 以跳過權限確認的模式搜尋並外送 secret（2025 年 8 月，Nx 事件）。對應 #1、#4、#5。
- 模型產生不存在的套件名稱，被搶註為惡意套件。對應 #5。

後三項的細節來自二手報導，未逐一核對原始來源。

## 不在範圍內

- 惡意的內部人員。兩位開發者被信任。
- 廠商端的資料處理。送進模型的內容受各廠商的條款約束。
- GitHub 本身被入侵。
