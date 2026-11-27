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
| guardrail 本身（workflow、policy、spec） | 被削弱後，其他防線失效 | 是，前提是有人發現 |
| 訂閱帳號的登入狀態 | 被竊取 | 可撤銷 |
| 未來的 production 與資料庫 | 被刪除或外洩 | 否 |

## 威脅與控制

| # | 威脅 | 硬性控制 | 軟性控制 |
|---|---|---|---|
| 1 | Agent 讀取 home 下的私人檔案 | VM 只掛載專案目錄，而且是唯讀；雲端 session 不在你的機器上 | `.claude/settings.json` 的 `denyRead`；guard hook |
| 2 | Agent 誤刪工作目錄以外的檔案（`rm -rf ~/`） | 同上：VM 內沒有那些檔案 | guard hook；專案不放在 iCloud 同步的目錄；備份 |
| 3 | Agent 使用機器上的雲端憑證 | VM 內沒有 `~/.aws` 等目錄 | deny rules 擋雲端 CLI |
| 4 | Prompt injection（repo 內容、issue、網頁、套件說明）誘使 agent 外送資料 | 建立在 deny-all 網路 preset 之上的 egress allowlist，每個 sandbox 啟動時都會從裡面探測（#40）；VM 內沒有值得外送的秘密，除了訂閱登入狀態，以及 Lima 備援中的 agent token。前提是專案目錄裡沒有 secret（#32） | AGENTS.md 第 7 條 |
| 5 | Agent 安裝惡意或不存在的套件（slopsquatting、被入侵的套件） | 依賴變更一律 T2，需人類核准才能合併：manifest、任何 `*.lock`、`*.lockb` 或 `*.lockfile`，以及 `.npmrc`、`pip.conf` 這類 registry 設定；安裝發生在 VM 內；egress allowlist 限制回連 | AGENTS.md 第 5 條 |
| 6 | Agent 直接 push main、force push、刪 branch | Ruleset `main`：main 只能經 PR 變更。Ruleset `main-merge`：只有 admin 與 Conductor App 能更新 main（**待驗證**）。Agent 以 GitHub App 的身分操作，只有被授予的權限，沒有 bypass | guard hook；deny rules |
| 7 | Agent 修改 CI 讓檢查通過 | Agent token 沒有 Workflows 權限；`.github/` 與掃描工具的設定（`.gitleaks.toml`、`.semgrepignore` 之類）在 CODEOWNERS；負責判定的 check 由 base branch 的那份工具以它的 policy 執行，並以 `python3 -I` 啟動；只有合併到 main 的 PR 會被判定；變更的路徑以 `git diff -z` 讀取，所以 git 原本會加上引號的路徑仍然對得上 policy 的 pattern | AGENTS.md 第 3 條 |
| 8 | Agent 削弱風險規則、prompt 或工具 | `policy/`、`prompts/`、`tools/` 在 CODEOWNERS，且為 T2 | 同上 |
| 9 | Agent 聲稱寫了測試但沒有，或寫了空測試 | `spec-verify`：traceability（依執行結果）與 red-green | 審查 agent 對測試有效性的稽核 |
| 10 | Agent 修改或刪除測試來遷就實作 | Spec 受 CODEOWNERS 保護；已通過的 TC 不得消失，即使它的 spec 在同一個變更裡被刪掉也一樣，除非人類把它列進 `docs/specs/retired.toml`；red-green，其中在 base 上被 skip 的測試，或 base 上沒有產生報告的執行，都不算紅；base 上 setup 指令失敗的執行，或在一份完全沒有失敗項目的 base 報告裡找不到的測試，也不算紅（最後這兩項依據的是執行 PR 程式碼的那個 job 寫出的檔案，見 #21） | 審查 agent 逐一檢查測試階段之後的測試變更 |
| 11 | Agent 悄悄更改需求 | `docs/specs/` 在 CODEOWNERS；新的 push 使舊核准失效 | |
| 12 | Agent 核准或合併自己的 PR | Agent 的 GitHub App 不可能是 code owner；PR 由 Conductor App 開啟；App 不能核准；`main-merge` ruleset 讓 agent 的 token 無法合併（#34） | deny rules 擋 `gh pr merge` |
| 13 | Agent 偽造 `agent-review` 的結果 | Agent token 沒有 commit status 權限；status 由一個從頭到尾看不到 PR 檔案的 `publish` job 寫入；判定結果寫在兩個 checkout 之外，而且只有 review 步驟成功時才算數，否則 status 是失敗；審查者在 default branch 的 checkout 裡以唯讀 token 執行，所以它的設定與 hooks 不會來自 PR；`--tools` 限制了審查者擁有的工具（**待驗證**）；required checks 必須由 GitHub Actions 回報（**待驗證**） | 審查者被它審查的文字說服而做出錯誤判定，這一點沒有防線。見 guideline 4 的說明：這是最弱的一環，硬性保證不依賴它 |
| 14 | Agent 自行部署或建立 release | Tag ruleset：`v*` 只有 admin 能建；release job 要求被打 tag 的 commit 上 `ci`、`security` 與 `spec-verify` 都存在而且是綠的；雲端只信任來自 tag 的 OIDC；沒有長期金鑰 | |
| 15 | Agent 刪除 production 資料庫或備份 | Agent 與 CI 沒有 production 憑證；部署角色沒有刪除備份的權限；migration 為 T2 | |
| 16 | Secret 被 commit | `security` check 的 gitleaks | AGENTS.md 第 6 條 |
| 17 | Conductor 失控：無限重試、大量開 PR | 每日 PR 上限、重試與 fix 輪數上限、WIP 上限；kill switch，由 Actions 上的 job 與本機 conductor 在每一輪即時讀取，讀不到時視為開啟（#43）；派工在送出之前先記錄，所以被中斷的執行不會把它送出兩次。交接前後重疊的兩個 conductor 仍然可能重複派工；每個 conductor 在每次派工之前都會重新讀取 lease，這縮小了範圍，但沒有消除它 | 每日 brief |
| 18 | 長時間運作後 agent 偏離指示 | 沒有長 session：每個 stage 是全新 context，狀態在 GitHub | |
| 19 | 模型升級後行為改變 | 排程是決定性程式；gate 是機械檢查 | 每週稽核抽樣 |
| 20 | Computer use、瀏覽器擴充、個人資料 connector 碰到私人資料 | 無。這些路徑不經過 VM | 規則：不開啟。見 guideline 3 |
| 21 | Agent 直接寫出假的測試結果檔，騙過 `spec-verify` | 無。測試結果本來就由 PR 的程式碼產生 | `Makefile` 受 CODEOWNERS 保護；審查 agent；每週抽查 |
| 22 | 雙語 story 的兩份語意不同：你核准的中文與 agent 實作的英文有出入 | 結構一致與同步變更由 `spec-lint` 強制 | PO 自我比對；另一廠商的 review agent 逐條比對 |
| 23 | PR 的程式碼在 self-hosted runner 上留下東西，影響之後的 job | Overflow 預設是關閉的（`overflow_runner = []`），所以 `ci` 與 `security` 在 GitHub-hosted runner 上執行；負責判定的 job 不論怎麼設定都不會移走 | 一旦你設定了 overflow runner 就沒有：沒有任何東西檢查它是否每個 job 都重建。見 #37 |
| 24 | 維護用的 session 被誘導去削弱 guardrail | guardrail 路徑的變更一律需要人類核准才能合併 | AGENTS.md 第 3 條：只有人類在 session 中直接提出才算維護要求 |
| 25 | Actions 額度被耗盡，gate 無法執行 | 額度用完時 PR 無法合併，不會在沒有 gate 的情況下合併 | 每日 brief 裡的用量估算。Overflow 預設是關閉的，所以沒有任何東西會自動緩解：在下個月開始或你加購之前，合併會停止 |
| 26 | Agent 在掛載的 repo 裡埋 git hook 或改 `.git/config`，等你下次在那裡使用 git 時在 Mac 上執行 | Clone 模式：repo 以唯讀掛載，agent 在自己的 clone 上工作 | Workspace 可寫時 `agentctl doctor --inside` 會警告 |
| 27 | Agent 利用被轉發的 SSH agent 以你的身分 push，繞過它自己的身分 | `sandbox/sbx.sh setup` 關掉 SSH agent forwarding；對外的 SSH 不在 allowlist 內 | 連得到帶有 key 的 SSH agent 時 `agentctl doctor --inside` 會判定失敗 |
| 28 | Agent 的 GitHub 憑證從 sandbox 內被竊取 | 使用 sbx 時 key 與 token 都不在 VM 內；host 上的 proxy 注入一小時的 token | Lima 備援中 key 在 VM 內；可在 App 的設定頁撤銷 |
| 29 | Agent 做了角色以外的事：審查或 triage 的 agent 修改程式，或拉進套件 | 它的 token 產生時就沒有 push 權限，它的 sandbox 也連不到套件 registry（`tools/agentctl/profiles.py`）；sandbox 絕不重複使用，所以它不會沿用另一個 stage 的網路規則。僅限 Docker Sandboxes 路徑 | Stage 的 prompt；harness 的 deny rules |
| 30 | Agent 在自己的 branch 上修改權限設定或 sandbox 腳本，替自己加權限 | Sandbox 由固定在 repo 之外的工具副本與 default branch 上的腳本建立 | 這些路徑屬於 guardrail：CODEOWNERS 與 T2。當 checkout 裡 host 上的腳本與 default branch 不同時，`sandbox/sbx.sh` 拒絕執行（#31） |
| 31 | 來自 PR 或 agent 的 branch 的程式在 Mac 上或在負責判定的 job 裡被執行：目前目錄裡一個取了 module 名稱的檔案（`agentctl.py`、`json.py`），或 host 腳本在那個 branch 上的版本 | `bin/agentctl`、CI 裡負責判定的 job 與 token helper 都以 `python3 -I tools/run.py` 啟動工具，目前目錄與 `PYTHONPATH` 因此不在 import 路徑上；負責判定的 job 執行的是 base branch 的那份工具；sandbox 由固定在 repo 之外的副本建立；本機 conductor 用 `origin/main` 的一份全新 checkout 裡的腳本啟動 sandbox；story id、stage 與 harness 在進入路徑、sandbox 名稱或指令之前都會先驗證 | 當 `sandbox/`、`tools/`、`bin/` 或 `policy/` 與 default branch 不同時，`sandbox/sbx.sh` 與 `agentctl conductor here` 拒絕執行。這防的是不小心從 agent 的 branch 執行它們這種意外。這項檢查本身是那些腳本的一部分，所以擋不住一個已經帶有惡意的 checkout。規則：host 上的腳本要從 default branch 的乾淨 checkout 執行 |
| 32 | 專案目錄裡的 secret 被 agent 讀到：clone 模式把整個目錄以唯讀掛進去，包含被忽略的檔案 | 對你自己放進去的檔案來說沒有。Pipeline 自己的憑證是從 repo 之外讀取的：`~/.config/agent-dev/<owner>-<repo>/conductor.env` 與 `~/.config/agent-app/`。共用的 skills store 已關閉（**待驗證**） | `sandbox/sbx.sh` 只要發現檔名看起來像 secret 的未追蹤檔案，不論是否被忽略（`.env*`、`*.pem`、`*.key`、`.npmrc` 與類似的檔名），就拒絕啟動 sandbox，也拒絕重新接上。它只看檔名，而且可以被略過。規則：專案目錄裡不放任何 secret |
| 33 | 握有憑證的 workflow 以某個 branch 上的那一版執行 | 憑證是 `conductor` environment 的 secret，只有 default branch 能使用，所以從其他任何 ref 啟動的執行拿不到（**待驗證**）；握有憑證的 workflow 都不由 `pull_request` 或 push 到 branch 觸發：`notify.yml` 沒有權限也沒有 secret，conductor 透過 `workflow_run` 對它做出反應；Claude 審查者只有在從 default branch dispatch 時才執行；agent token 沒有 Workflows 權限 | 這個 environment 與它的 branch 規則是安裝時手動建立的。如果 secret 被建立成 repo secret，就沒有這層保護 |
| 34 | Agent 用自己的 token 開 PR、改 PR 的 base 或合併 PR | 開 PR、改 base 與送出 review：能 push 的 token 只有 pull requests: read（`tools/agentctl/profiles.py`）。合併是另一道控制：GitHub 的 merge endpoint 只需要 contents: write，而這個 token 有這個權限，所以擋住合併的是 `main-merge` ruleset，它只讓 admin 與 Conductor App 更新 main；`main` ruleset 沒有 bypass（**待驗證**：token 的縮小，以及兩個 ruleset 的疊加）。僅限 Docker Sandboxes 路徑 | deny rules 擋 `gh pr create`、`gh pr review` 與 `gh pr merge`。沒有涵蓋的部分：審查用的 token 可以寫入 PR，不過它不能 push 也不能合併；雲端 session 以你連結的帳號操作 |
| 35 | Agent 偽造 conductor 的 marker 留言，假裝有一次派工、取消一次派工，或讓通知不再發出 | Marker 只有在出自 conductor 自己的帳號，或 `policy/roles.toml` 所列的人類時才被採信；`roles.toml` 讀的是 default branch 上的版本 | 無。沒有涵蓋的部分：雲端 session 以你的帳號操作，而你的帳號是名單上的人類，所以它寫的 marker 會被採信。帳號名稱與 Conductor App 的 slug 相同的人也會被採信；這個人必須是 collaborator 才能留言 |
| 36 | 過期或錯誤的 PR 被當成 story 的 PR：已關閉的、目標是其他 base 的、來自 fork 的 | Conductor 只選從本 repo 合併到 default branch 的開啟中 PR，沒有的話才選已合併的，而且只認 spec 定義的 branch 名稱（`story/NNN-slug`）；目標是其他 base 的 PR 不算那個 branch 的 PR，所以真正的那一個仍然會被開啟；fix、解衝突與 review 都綁定在派工當時的 commit 上，每個新的 commit 都需要自己的判定；PR 若不是開啟中、來自本 repo、以 default branch 為目標，review workflow 會拒絕；`ci`、`security` 與 `risk-gate` 只針對合併到 main 的 PR 執行 | |
| 37 | PR 的程式碼在一個共用、長駐、存有登入狀態的 runner 上執行：它改防火牆、讀取登入狀態，或留存到之後的 job | Overflow 預設是關閉的，所以 `ci` 與 `security` 不會在 Lima VM 的 runner 上執行；那個 runner 不屬於支援的安裝路徑 | 一旦你設定了 `overflow_runner` 就沒有：policy 檔寫明 runner 必須專用、不帶憑證、每個 job 都重建，但沒有任何東西強制這一點 |
| 38 | 帶有惡意的結果 artifact 把檔案導向判定程式所在的 checkout：執行 PR 程式碼的 job 在 `reports/` 裡留下一個 symbolic link，解開時跟著它走 | `spec-verify` 把 artifact 解開在 runner 的暫存目錄裡，位於兩個 checkout 之外；只有一般的 `*.xml` 檔與 `collected.json` 會被往下傳；其中任何地方出現 symbolic link 都會讓 job 失敗；提供判定程式的 base branch 最後才 checkout（**待驗證**：`actions/download-artifact` 遇到帶有惡意的壓縮檔時的行為） | 無。沒有涵蓋的部分：被往下傳的檔案，內容仍然是 PR 的 job 寫出來的東西（#21） |
| 39 | Agent 修改 PR 上的 `tier:` label，讓較高分級的變更被自動合併 | Conductor 讀取分級的來源是 `risk-gate` 寫在 head commit 上的 commit status `risk-tier/*`，不是 label；agent token 沒有 commit status 權限；找到的 status 中採用最嚴格的那個，一個都沒有就視為 T2；auto-merge 只針對做出決定時的那個 commit 啟用（`--match-head-commit`）；T2 變更在人類核准之前，`risk-gate` 也一直是紅的（**待驗證**：這些 status 是否出現在 `statusCheckRollup`，以及 `--match-head-commit`） | Label 仍然存在，只給人看。Agent 的 token 有 issues: write，仍然改得動它 |
| 40 | Setup 之後 sbx 的網路 preset 不再是 deny-all，或已經存在的 sandbox 保留了比它的 stage 所允許的更寬的規則 | 無。Preset 是整台機器共用的，這個 repo 裡沒有任何東西把它固定住，也沒有任何東西讀回執行中 sandbox 的規則 | `sandbox/sbx.sh` 每次建立 sandbox，以及每次重新接上互動式 sandbox 時，都會從 sandbox 內探測（`https://example.com/`，不需要建置的 stage 另外再探測 `https://registry.npmjs.org/`），任何一個連得上，或無法探測時，就拒絕；`AGENT_SKIP_NETWORK_PROBE=1` 只能略過後面這種情況。`setup` 留下的標記只是為了方便。沒有涵蓋的部分：sandbox 接上期間發生的變更；探測的兩個主機以外的任何主機；重新接上時依賴的是 agent 已經用過的 sandbox 裡的 `curl`（**待驗證**：在真實 sandbox 內） |
| 41 | Review 的判定被發布在 conductor 要求的 commit 以外的 commit 上，或同一個要求跑了第二次 review | Conductor 把記在派工 marker 裡的 commit 傳進去（`sha`）；job 開始時如果 PR 的 head 是另一個 commit，job 會在審查之前失敗，不發布任何東西；status 寫在被審查的那個 commit 上，每個新的 commit 都需要自己的判定（#36）；`agent-review` 完成時會喚醒 conductor，由它針對新的 head 重新要求（**待驗證**：`agent-review` 的 `workflow_run`） | 無。沒有涵蓋的部分：在那項檢查之後、review 執行期間才進來的 push。這時判定落在較舊的 commit 上，新的 head 仍然需要自己的判定 |
| 42 | 具名開發者的 story 悄悄地用了另一個人的憑證執行 | Sprint 檔為 story 指定了開發者時，只使用 `NAME_<LOGIN>`（`tools/agentctl/github.py` 的 `secret`）；不帶後綴的 `NAME` 用在屬於 `default` 的 story，以及開發者自己的 Mac 上屬於他自己的 story；secret 不存在時，派工會在寫入任何東西之前失敗；review workflow 對具名開發者只使用 `CLAUDE_CODE_OAUTH_TOKEN_<LOGIN>`；本機 conductor 會延後其他開發者的 story | 無。沒有涵蓋的部分：沒有任何東西檢查存在 `NAME_<LOGIN>` 底下的值是否真的是那個人的憑證 |
| 43 | 讀不到的 kill switch 被當成「沒有暫停」；或已經開啟的 auto-merge 在暫停之後繼續生效 | Repo variable 透過 API 讀取，讀取失敗時會拋出錯誤，不會被讀成沒有設定；`CONDUCTOR_PAUSED` 讀不到時，conductor 的行為等同暫停；在 Actions 上，lease 的 variable 讀不到時，這次執行什麼都不做；暫停中的 conductor 會把每個已經開啟 auto-merge 的開啟中 PR 的 auto-merge 關掉（**待驗證**：以 Conductor App 的身分執行 `gh pr merge --disable-auto`） | 規則：要立刻停止，請同時手動執行 `gh pr merge NUMBER --disable-auto`。沒有涵蓋的部分：auto-merge 是在暫停中的 conductor 下一輪執行時才被撤回，不是在設定 variable 的當下，所以在那一輪之前 check 就變綠的 PR 仍然會被 GitHub 合併 |

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
