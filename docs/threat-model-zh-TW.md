# 威脅模型

*English: [threat-model.md](threat-model.md)。兩份內容不一致時以英文版為準。*

每一列是一類已經真實發生或可以預期會發生的事件，並對應到能阻止它的控制。控制分為兩種。**硬性**控制由環境或 GitHub 強制執行，agent 無法繞過。**軟性**控制可以被繞過，只作為第二層。控制背後的設計在 [guideline-zh-TW.md](guideline-zh-TW.md)；「Layer」欄說明由哪一層的 checklist 測試該控制。

編號是固定的：已撤回的編號（17 的 lease、28 的 Lima 案例、37）不會再使用，內容有變動的列保留原編號。標示 **To verify** 的控制，是依據文件或推論而來，尚未在真實的 GitHub、Docker Sandboxes 或 Mac 上執行過（見[指南](guideline-zh-TW.md)）。

## Assets

| Asset | Worst case | Recoverable? |
|---|---|---|
| Mac 上的私人資料 | 被讀取並帶入某個廠商的 context，或被送到外部 | 否 |
| Mac 上工作目錄以外的檔案 | 被刪除或覆寫 | 可從備份還原 |
| 暫時有效的雲端 CLI token | 在有效期間內被用來操作雲端資源 | 視操作而定 |
| repository 的歷史與 main | 被改寫，或被合併進有問題的程式碼 | 可以（git），但代價很高 |
| 護欄本身（workflow、`agentdev.toml`、spec） | 一旦被削弱，其他防線都會失效 | 可以，前提是有人發現 |
| Mac 上安裝的 kit，以及專案所固定的 kit 版本 | 被替換，使攻擊者選定的程式碼在 Mac 或 judge 上執行 | 發現的話可以；Mac 可能已被入侵 |
| conductor 的憑證（Conductor App 的金鑰、dispatch secret） | 被用來以 pipeline 的身分開啟、以 merge 代為核准或 dispatch | 可撤銷；期間造成的損害無法撤銷 |
| 訂閱帳號的登入狀態 | 被竊取 | 可撤銷 |
| 未來的正式環境與資料庫 | 被刪除或外洩 | 否 |

## Threats and controls

| # | Layer | Threat | Hard controls | Soft controls |
|---|---|---|---|---|
| 1 | 1 | agent 讀取 home 底下的私人檔案 | microVM 只以唯讀方式掛載專案 repository；雲端 session 不在你的機器上 | harness 的 deny rule（`agentctl harness-settings`）；專案的 guard hook |
| 2 | 1 | agent 誤刪工作目錄以外的檔案（`rm -rf ~/`） | 同上：那些檔案不在 VM 內 | guard hook；專案不放在 iCloud 同步的目錄；備份 |
| 3 | 1 | agent 使用機器上的雲端憑證 | VM 內不存在 `~/.aws` 之類的目錄 | deny rule 封鎖雲端 CLI |
| 4 | 1 | prompt injection（repository 內容、issue、網頁、套件說明）誘使 agent 把資料送出去 | 在 deny-all 網路 preset 之上加 egress allowlist，並在每個 sandbox 建立時從內部探測（#40）；VM 內除了訂閱登入狀態之外，沒有值得外送的 secret。這以專案目錄內沒有 secret 為前提（#32） | 專案 `AGENTS.md` 的規則 7（repository 內容是資料） |
| 5 | 2, 3 | agent 安裝惡意或不存在的套件（slopsquatting、被入侵的套件） | 變更 `[risk.t2] dependency_manifests` 內的 manifest 或 lock 檔一律為 T2，需要人工核准才能 merge；安裝在 VM 內進行；egress allowlist 限制往外的呼叫 | 專案 `AGENTS.md` 的規則 5。未涵蓋：這份清單必須由專案依自己的技術堆疊補充；未列名的 manifest 不屬於 T2 |
| 6 | 2 | agent 直接 push 到 main、force-push 或刪除 branch | ruleset `main`（layer 2）：main 只能透過 pull request 變更。ruleset `main-merge`：只有 admin 與 Conductor App 可以更新 main（**To verify**）。agent 以 GitHub App 的身分行動，只有被授予的權限，沒有 bypass | guard hook；deny rule |
| 7 | 2, 3 | agent 修改 CI 讓檢查通過 | agent token 沒有 Workflows 權限；`.github/**` 與掃描器設定是護欄（CODEOWNERS 與 T2），`agentdev.toml` 亦然；judge 檢查以固定的 SHA 執行 kit，並使用 base branch 的設定；只有進入 main 的 pull request 會被評判；變更的路徑以 `git diff -z` 讀取，所以 git 原本會加引號的路徑仍然能符合規則 | 專案 `AGENTS.md` 的規則 3 |
| 8 | 2, 3 | agent 削弱風險規則或 kit 版本 | 風險規則與 pin 都在 `agentdev.toml`，這是一律為 T2 的護欄；prompt 與工具根本不在專案內，而在已安裝的 kit 中固定的 SHA 上（#46、#47） | 同上 |
| 9 | 3 | agent 聲稱寫了測試但其實沒有，或寫了空測試 | `spec-verify`：可追溯性（依據執行結果）與 red-green | review agent 的忠實度稽核。它也是唯一能抓到「測試在 main 與在 branch 上行為不同」（例如檢查某個檔案是否存在）的機制：red-green 只能顯示 story 的測試在 main 上沒有通過，而測試本身就是 pull request 的程式碼 |
| 10 | 3 | agent 修改或刪除測試以配合實作 | spec 受 CODEOWNERS 保護；在 main 上最近最多五次 `ci` 執行中任一次通過過的 TC 不得消失，即使它的 spec 在同一個變更中被刪除，除非人工把它列在 `retired.toml`；red-green 中，在 base 上被跳過的測試或沒有報告的 base 執行不算 red，base 執行的 setup 指令失敗也不算，base 報告中缺少某個測試、而且沒有任何失敗屬於該 story 自己的測試檔，也不算（最後兩項依賴於執行 pull request 程式碼的 job 所寫的檔案；見 #21） | review agent 逐一檢查 tests stage 之後做的每一項測試變更 |
| 11 | 2 | agent 悄悄更改需求 | spec、sprint 與產品文件在 CODEOWNERS 與 T2 之中；新的 push 會使先前的核准失效 | |
| 12 | 1, 2 | agent 核准或 merge 自己的 pull request | agent 的 GitHub App 不能成為 code owner；pull request 由 Conductor App 開啟；該 App 不能核准；`main-merge` ruleset 使 agent 的 token 無法 merge（#34） | deny rule 封鎖 `gh pr merge` |
| 13 | 3 | agent 偽造 `agent-review` 的結果 | agent token 沒有 commit status 權限；status 由一個從不接觸 pull request 檔案的 `publish` job 寫入；verdict 寫在兩個 checkout 之外，且只有在 review 步驟成功時才算數，否則 status 為 failure；reviewer 在預設 branch 的 checkout 中以唯讀 token 執行，所以它的設定與 hook 不來自 pull request；reviewer 的工具清單受到限制（**To verify**）；必要檢查（ruleset `main-checks`，layer 3）必須由 GitHub Actions 回報（**To verify**） | 無法防止 reviewer 被它所審閱的文字說服而給出錯誤的 verdict。見指南第 6 節：這是最弱的一環，硬性保證不依賴它 |
| 14 | 2 | agent 自行部署或建立 release | ruleset `tags`：只有 admin 能建立、移動或刪除任何 tag；專案的 release job（它自己的檔案，來自範本）要求被標記的 commit 上檢查都存在且為綠燈；雲端只信任來自 tag 的 OIDC；沒有長效金鑰 | |
| 15 | 2 | agent 刪除正式資料庫或其備份 | agent 與 CI 沒有正式環境的憑證；部署角色沒有刪除備份的權限；migration 是 T2（`high_risk`） | |
| 16 | 3 | secret 被 commit | `security` 檢查中的 gitleaks | 專案 `AGENTS.md` 的規則 6 |
| 17 | 4 | conductor 失控：無止盡的重試、大量開 pull request | 每日 pull request 上限、重試次數、fix round 與 triage 的上限、work-in-progress 上限、stage 逾時；kill switch `CONDUCTOR_PAUSED`，每次 pass 即時讀取，讀不到時視為開啟（#43）；dispatch 先記錄再送出，所以被中斷的 pass 不會重複送出；lock 檔限制每個專案每台 Mac 只有一個 conductor；連續三次 pass 失敗後，conductor 在每次 pass 之間等待 15 分鐘 | 每日 brief。未涵蓋：另一台 Mac 上的第二個 conductor（#48） |
| 18 | 4 | agent 長時間執行後偏離它的指示 | 沒有長時間的 session：每個 stage 都是全新的 context，狀態存放在 GitHub | |
| 19 | 3, 4 | model 升級後行為改變 | 排程是確定性的程式碼；gate 是機械式檢查 | 每週抽樣稽核 |
| 20 | 1 | computer use、瀏覽器擴充功能或個人資料 connector 接觸到私人資料 | 無。這些路徑不經過 VM | 規則：不要開啟。見指南第 4 節 |
| 21 | 3 | agent 直接寫出假的測試結果檔，騙過 `spec-verify` | 無。測試結果本來就是由 pull request 的程式碼產生的 | `test_cmd` 執行的檔案與任何程式碼一樣會被審閱；review agent；每週抽查 |
| 22 | 3 | 雙語 story 的兩個版本在意義上不同 | 結構相符與兩者同時變更由 `spec-lint` 強制執行 | PO 自己的比對；review agent 逐項比對 |
| 23 | 3 | pull request 的程式碼在持有登入資訊、長期存在的共用 runner 上留下東西：改防火牆、讀取登入資訊，或延續到後續的 job | kit 不含任何 self-hosted runner。`overflow_runner` 預設為空，所以 `ci` 與 `security` 在 GitHub 代管的 runner 上執行；負責判斷的 job 無論怎麼設定都不會移動 | 一旦你設定 overflow runner 就沒有：沒有任何機制檢查它是專用的、不含憑證、而且每個 job 都重建 |
| 24 | 2 | maintenance session 被誘使削弱護欄 | 變更護欄路徑一律需要人工核准才能 merge | 專案 `AGENTS.md` 的規則 3：只有人直接在 session 中提出的要求才算 maintenance 要求 |
| 25 | 3 | Actions 額度用完，gate 無法執行 | 額度用完時，pull request 無法 merge；沒有通過 gate 的東西不會被 merge | 每日 brief 中的用量估計。overflow 是關閉的，所以沒有任何東西會自動紓解：merge 會停止，直到下個月或你付費增加額度 |
| 26 | 1 | agent 在掛載的 repository 中植入 git hook 或編輯 `.git/config`，下次你在那裡使用 git 時就在 Mac 上執行 | Clone mode：repository 以唯讀方式掛載，agent 在私有的 clone 上工作 | 工作區可寫入時，`agentctl doctor --inside` 會警告 |
| 27 | 1 | agent 使用你轉發的 SSH agent 以你的身分 push，繞過它自己的身分 | `agentctl sandbox setup` 關閉 SSH agent 轉發；對外的 SSH 不在 allowlist 內 | 能連到帶有金鑰的 SSH agent 時，`agentctl doctor --inside` 會失敗 |
| 28 | 1 | agent 的 GitHub 憑證在 sandbox 內被竊取 | VM 內既沒有 App 的金鑰，也沒有長效 token；host 上的 proxy 注入一小時有效的 token | token 有效一小時，並可在 App 設定中撤銷 |
| 29 | 1 | agent 越出它的角色行事：reviewer 或 triage agent 修改程式碼或引入套件 | 它的 token 在產生時就沒有 push 權限，它的 sandbox 連不到套件 registry（`tools/agentctl/profiles.py`）；sandbox 絕不重複使用，所以無法繼承其他 stage 的網路規則。僅限 sandbox 路徑 | stage prompt；harness 的 deny rule |
| 30 | 1 | agent 在它的 branch 上編輯 token profile 或 sandbox 腳本，擴大自己的權限 | 這些是已安裝 kit 的一部分，在專案之外且唯讀，launcher 從預設 branch 取得版本（#46） | |
| 31 | 1, 4 | pull request 或 agent branch 的程式碼在 Mac 或 judge job 上執行：目前目錄中名稱像模組的檔案（`agentctl.py`、`json.py`），或 branch 版本的 host 腳本 | 專案目錄樹中沒有 host 程式碼。launcher 與 `tools/run.py` 以 `python3 -I` 啟動 kit，使目前目錄與 `PYTHONPATH` 不在 import 路徑上；conductor 從 `origin/main` 的全新 worktree 讀取 spec 與設定；judge 以固定的 SHA 執行 kit；story id、stage 與 harness 在進入路徑、sandbox 名稱或指令之前都會先驗證 | 不需要：原本檢查 checkout 是否可信的機制，隨它所保護的程式碼一併移除了 |
| 32 | 1 | 專案目錄內的 secret 被 agent 讀取：clone mode 以唯讀方式掛載整個目錄，包含被忽略的檔案 | 對你自己放進去的檔案，無。pipeline 自己的憑證從 repository 之外讀取：`~/.config/agent-dev/<owner>-<repo>/conductor.env` 與 `~/.config/agent-app/`。共用的 skills store 已關閉（**To verify**） | 只要有任何未追蹤的檔案（無論是否被忽略）名稱看起來像 secret，`sbx.sh` 就拒絕啟動 sandbox。它依檔名判斷，可以被覆寫。規則：專案目錄內不要放任何 secret |
| 33 | 2, 3 | 持有憑證的 workflow 以它在某個 branch 上的版本執行 | 憑證是 `conductor` environment 的 secret，只有預設 branch 能使用，所以來自其他 ref 的執行拿不到任何憑證（**To verify**）；持有憑證的 workflow 都不會被 push 到 branch 觸發；Claude reviewer 只在從預設 branch dispatch 時執行；agent token 沒有 Workflows 權限 | environment 與它的 branch 規則是在 setup 時手動建立的。若改建成 repository secret，就沒有這種保護 |
| 34 | 1, 2 | agent 以自己的 token 開啟、改目標或 merge pull request | 開啟、改目標與 review：負責 push 的 token 只有 pull requests: read。Merge 是另一種控制：GitHub 的 merge endpoint 只需要 contents: write，而該 token 有，所以擋下 merge 的是 `main-merge` ruleset，它只讓 admin 與 Conductor App 更新 main；`main` ruleset 沒有 bypass（**To verify**：縮減 token 的權限，以及兩個 ruleset 的疊加）。僅限 sandbox 路徑 | deny rule 封鎖 `gh pr create`、`gh pr review` 與 `gh pr merge`。未涵蓋：review token 可以對 pull request 寫入，雖然它不能 push 或 merge；雲端 session 以你連接的帳號行事 |
| 35 | 4 | agent 偽造 conductor 的 marker comment，以假造 dispatch、取消 dispatch 或使通知靜音 | marker 只有在由 conductor 自己的 login，或由列在 `[roles]`（從預設 branch 讀取）的人所寫時才被採信 | 無。未涵蓋：雲端 session 以你的帳號行事，而你是列名的人，所以它寫的 marker 會被採信。login 與 Conductor App 的 slug 相同的人也會被採信；但那個人必須是 collaborator 才能留言 |
| 36 | 3, 4 | 過時或錯誤的 pull request 被當成該 story 的：已關閉的、進入其他 base 的、來自 fork 的 | conductor 只選擇開啟中的 pull request，否則選擇已 merge 的，且必須是從這個 repository 進入預設 branch，並且只認 spec 定義的 branch 名稱（`story/NNN-slug`）；fix、衝突解決與 review 都綁定到它們被 dispatch 時的 commit，每個新 commit 都需要自己的 verdict；review workflow 拒絕不是開啟中、不是同 repository、或不是進入預設 branch 的 pull request；`ci` 與 `security` 只對進入 main 的 pull request 執行；對進入其他 base 的 pull request，`risk-gate` 會失敗而不是被跳過，因為 GitHub 把被跳過的 job 算成通過的必要檢查；未經 push 就改目標到 main 的 pull request，沒有 `ci`、`security` 或 `spec-verify` 的結果，並保持被擋住，直到下一次 push（**To verify**） | |
| 38 | 3 | 惡意的結果 artifact 把檔案導向 judge 的 checkout：執行 pull request 程式碼的 job 在 `reports/` 留下 symbolic link，解壓縮時跟著連結走 | `spec-verify` 在 runner 的暫存目錄中解壓縮 artifact，位於兩個 checkout 之外；只有單純的 `*.xml` 檔與 `collected.json` 會被傳下去；其中任何位置的 symbolic link 都會使 job 失敗；提供 judge 設定的 base branch 最後才 checkout（**To verify**：`actions/download-artifact` 面對惡意壓縮檔時的行為） | 無。未涵蓋：被傳下去的檔案內容，仍然是 pull request 的 job 寫了什麼就是什麼（#21） |
| 39 | 4 | agent 編輯 pull request 上的 `tier:` label，使較高 tier 的變更被 auto-merge | conductor 從 `risk-gate` 寫在 head commit 上的 commit status `risk-tier/*` 讀取 tier，而不是從 label 讀取；agent token 沒有 commit status 權限；可能有多個 status：取最嚴格的，這只會使 conductor 更謹慎，找不到任何 status 時視為 T2；只有描述為針對這個 pull request 與預設 branch 的「pull request #N into BRANCH」的 status 才算；auto-merge 只對做出決定的那個 commit 啟用（`--match-head-commit`）；T2 變更也使 `risk-gate` 保持紅燈，直到有人核准（**To verify**：`statusCheckRollup` 中出現的 status，以及 `--match-head-commit`） | label 仍然存在，但只給人看。agent 的 token 有 issues: write，仍然可以更改它 |
| 40 | 1 | sbx 網路 preset 在 setup 之後不再是 deny-all，或已存在的 sandbox 保有比它的 stage 所允許的更寬的規則 | 無。preset 是整台機器共用的，kit 內沒有任何東西固定它，也沒有任何東西讀回執行中 sandbox 的規則 | `sbx.sh` 在每次建立時從 sandbox 內發出最多三個請求：`https://github.com/`（在 allowlist 內）必須回應 2xx 或 3xx，否則無法區分「被拒絕」與「沒有網路」，腳本就停止；接著是 `https://example.com/`，以及對不 build 的 stage 的 `https://registry.npmjs.org/`：回應 2xx 或 3xx 表示可連到，腳本拒絕；沒有回應，或回應 4xx 或 5xx，視為被拒絕。缺少 `curl` 或 `sbx exec` 失敗是「無法檢查」；`AGENT_SKIP_NETWORK_PROBE=1` 只覆寫「無法檢查」。未涵蓋：這是對三個 host 的抽查，不是證明實際生效的 allowlist 等於專案的清單；來源自己的伺服器回應的 403 或 5xx 看起來像政策拒絕；sandbox 執行期間所做的變更（**To verify**，在真實機器上：被 sbx proxy 拒絕的請求從內部看起來是什麼樣子） |
| 41 | 3, 4 | review verdict 被發布到不是 conductor 所問的那個 commit，或同一個請求執行了第二次 review | conductor 傳遞 dispatch marker 中記錄的 commit（`sha`）；如果 job 開始時 pull request 的 head 是不同的 commit，job 會在 review 之前失敗，什麼都不發布；status 寫在被 review 的 commit 上，每個新 commit 都需要自己的 verdict（#36）；conductor 注意到 review 完成後，會針對新的 head 再次發出請求 | 無。未涵蓋：在該檢查之後、review 執行期間才送達的 push。此時 verdict 在較舊的 commit 上，新的 head 仍然需要自己的 verdict。對於由留言啟動或在本機 sandbox 中執行的 review，prompt 會指名 commit 並告訴 reviewer 在 head 不同時停止；那是對 agent 的指示，不是強制執行 |
| 42 | 2, 4 | 指定開發者的 story 悄悄以另一個人的憑證執行 | 對於 sprint 檔指名了開發者的 story，只使用 `NAME_<LOGIN>`；純 `NAME` 用於 `default` 的 story，以及開發者自己的 Mac 上該開發者的 story；缺少 secret 時，dispatch 在寫入任何東西之前就失敗；review workflow 對指名的開發者只使用 `CLAUDE_CODE_OAUTH_TOKEN_<LOGIN>`；conductor 延後其他開發者的 story | 無。未涵蓋：沒有任何機制檢查 `NAME_<LOGIN>` 底下存的值真的是那個人的憑證 |
| 43 | 4 | 讀不到的 kill switch 被當成「沒有暫停」；或已開啟的 auto-merge 在暫停後仍繼續 | repository variable 透過 API 讀取，讀取失敗時會丟出錯誤，而不是被當成未設定；`CONDUCTOR_PAUSED`、`CONDUCTOR_BOT` 與 `CONDUCTOR_QUOTA` 先一起讀取，只要有任何一個讀不到，該次 pass 就視為暫停，並且仍然撤回 auto-merge；暫停的 pass 會對每個開啟了 auto-merge 的開啟中 pull request 關閉 auto-merge，格式錯誤的 `CONDUCTOR_QUOTA` 項目會逐項被忽略（**To verify**：以 Conductor App 身分執行 `gh pr merge --disable-auto`） | 規則：要立即停止，也要手動執行 `gh pr merge NUMBER --disable-auto`。未涵蓋：「dispatch 已停止」不等於「auto-merge 已撤回」。後者需要一次能列出 pull request 並成功呼叫 GitHub 的 pass，而且發生在 conductor 下次執行時，而不是設定 variable 時；Mac 關機時就不會發生 |
| 44 | 4 | auto-merge 在後續的 push 之後仍保持啟動狀態，使 GitHub 合併了沒有人決定過的 commit | GitHub 仍然要求新的 commit 通過全部五個必要檢查；`risk-gate` 使 T2 commit 失敗，直到有人核准；每次 pass，conductor 都會對不再符合啟用條件的 story pull request 撤回 auto-merge（不是 draft、沒有待處理的人工 review、四個機械式檢查與 `agent-review` 為綠燈、tier 在 `auto_merge_tiers` 內），main 為紅燈、計畫損壞或 story 不在 sprint 內時也會撤回，即使該次 pass 提早返回，並在它符合條件時再次啟用（**To verify**：GitHub 是否在 push 之後保留該請求，以及撤回的行為） | 無。未涵蓋：push 與下一次 pass 之間的時間窗，在這段期間請求仍然處於啟動狀態。能通過的是 tier 高於已啟用的 tier、但低於 T2 的 commit（只啟用 T0 時的 T1），而且它在 conductor 執行之前就通過了 `ci`、`spec-verify` 與 `agent-review`。 |
| 45 | 3 | 在 draft pull request 上被跳過的檢查被算成通過 | draft 不能被 merge；把它標為 ready（`ready_for_review`）會對同一個 commit 觸發 `ci`、`security` 與 `spec-verify` 的完整執行（**To verify**：在 pull request 變成可 merge 之前，新的執行會取代被跳過的結果） | |
| 46 | 1, 4 | Mac 上安裝的 kit 被替換，或 agent 的 branch 選擇了在 Mac 上執行的 kit 版本 | 版本以完整的 commit SHA 解壓縮到 `~/.local/share/agent-dev-kit/versions/<sha>/` 並設為唯讀；launcher 從專案預設 branch 的 `agentdev.toml`（`origin/HEAD`，以最近一次 fetch 為準）取得版本，絕不從 working tree 取得，並且只接受完整的 40 字元 SHA；pin 只能透過經人工核准的 pull request 變更（T2） | 未涵蓋：以你的身分在 Mac 上執行的程序可以改變該目錄（`chmod`），因此可以改變已安裝的 kit；Mac 本身不在模型範圍內。pin 的新舊程度取決於你最後一次 `git fetch`，所以別人 merge 的 pin 在你 fetch 之前不會被使用。你自己設定的 `AGENTDEV_KIT_VERSION` 會覆寫 pin |
| 47 | 3 | caller workflow 呼叫的 kit 版本與 `agentdev.toml` 所 pin 的不同，或 branch 編輯 caller 使它呼叫自己的程式碼 | 在 `ci` 的 lint 步驟中執行的 `agentctl pins`，除非每個 caller 的 `uses: ...@<sha>` 與 `kit_version` 都等於 `[kit] version`，否則會失敗；caller 在 `.github/**` 底下，是護欄，因此是 T2；reusable workflow 以那個確切的 SHA 從 codeload 取得 kit，所以移動 branch 或 tag 不會改變任何事；judge job 從 base branch 讀取設定（**To verify**：在真實的 GitHub 上） | 無。未涵蓋：經人工核准、但本身有問題的 kit commit；commit 的 SHA 對每個 pin 它的專案都是永久的，所以修正是新的 SHA，以及在每個專案中各一個新的 pull request。`agentctl pins` 在 `ci` 內執行，所以在 pull request 上是由該 pull request 自己的 `ci` job 來評判，它是一致性檢查，本身不是防禦：防禦在於該變更是 T2 |
| 48 | 4 | 同一個專案在另一台 Mac 上有第二個 conductor，或 conductor 留在你不再使用的 Mac 上執行，兩者 dispatch 同一個 stage，或其中一個設定了另一個意料之外的 marker | lock 檔阻止同一台 Mac 上同一專案的第二個 conductor；dispatch 先記錄再送出，送出失敗時撤回，所以 dispatch 可能重複，但不會遺失；conductor 的憑證屬於單一開發者，這限制了失控的 conductor 能啟動的東西 | 無。沒有任何機制偵測另一台 Mac 上的 conductor。story 可能因此被 dispatch 兩次；gate 仍然適用於被 push 的任何東西。只在一台 Mac 上執行 `agentctl conductor`，並在其他地方停止它 |

## Reference incidents

設計期間參考的公開事件類型，用來檢查上表有無缺漏：

- 一個 agent 在被明確要求停止做變更之後，仍刪除了正式資料庫（2025 年 7 月，Replit 與 SaaStr）。對應 #14、#15。
- 一個 agent 透過雲端平台的 API 刪除了資料庫及其備份（2026 年 4 月的報導）。對應 #3、#15。
- 一個被入侵的 npm 套件，指示本機的 AI CLI 在略過權限提示的模式下搜尋 secret 並送出去（2025 年 8 月，Nx 事件）。對應 #1、#4、#5。
- 一個 model 產生了不存在的套件名稱，該名稱隨後被註冊為惡意套件。對應 #5。

最後三項的細節來自二手報導，沒有逐一對照原始來源查證。

## Out of scope

- 惡意的內部人員。專案上的人是被信任的。
- 被入侵的 Mac。如果有程序以你的身分在執行 conductor 的 Mac 上執行，它可以讀取 conductor 的金鑰並更改已安裝的 kit。kit 限制 agent 能接觸到的東西；它不保護已經是敵對的 host。
- 廠商端的資料處理。送給 model 的內容由各廠商的條款規範。
- GitHub 本身，或 Docker Sandboxes 隔離機制的入侵。假設 sandbox 是有效的；它的網路過濾只做抽查（#40），僅此而已。
