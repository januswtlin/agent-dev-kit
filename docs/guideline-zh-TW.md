# AI Coding Agent 開發環境 Guideline

*English: [guideline.md](guideline.md)。兩份內容不一致時以英文版為準。*

這份文件說明這個 repo 的設計：為什麼這樣做、各部分如何配合、哪些已驗證、哪些還沒有。
安裝步驟在 [runbook.md](runbook.md)，威脅與對應的控制在 [threat-model.md](threat-model.md)。

## 1. 目標

1. **Agent 碰不到你的私人資料，也造不成不可挽回的破壞。** 依嚴重性：讀取私人檔案（讀了就收不回）、誤刪工作目錄以外的檔案、使用機器上暫時有效的雲端憑證、未來的 production。
2. **人類注意力是瓶頸。** 你是 director：決定做什麼、核准範圍、放行上線。你不讀一般的 PR、不做 merge、不派工。

對團隊組成不做固定假設。一個人加一種 AI 訂閱就能用；一個人用多種，或多人各自帶不同的 AI 也可以。誰能核准產品決定、每個人的每個 stage 用哪個 harness，都是設定（`policy/roles.toml`、`.github/CODEOWNERS`）。不變的前提只有兩個：agent 用訂閱額度執行，不用按量付費的 API key；repo 所在的 GitHub 方案能在 private repo 上強制 ruleset。

## 2. 三個原則

**用能力邊界防護，不靠 agent 自律。** Prompt、permission 設定、指令黑名單都可能被繞過，只當第二層。真正的保證是：agent 所在的環境裡不存在能造成損害的東西。它看不到你的 home，手上的 token 沒有危險的權限。

**GitHub 是唯一的 control plane。** 所有 harness 只透過 branch、PR、issue 交接。換模型、換廠商、加入本地模型都不改變流程，也因此不需要 API key：每家模型在自家的 harness 裡用訂閱額度執行。

**機械檢查優先於 agent 的自述。** Agent 會過早宣告完成，也會高估自己的產出。凡是能用程式驗證的（測試是否真的存在並執行、是否真的驗到行為），就不問 agent。

## 3. 信任區域

| Zone | 內容 | Agent 能做什麼 |
|---|---|---|
| 0 你的 Mac | 私人資料、瀏覽器、Keychain、暫時有效的雲端 token、Ollama | Coding agent 不在這裡執行 |
| 1 Sandbox | 本機的 VM，或廠商的雲端 session。只有專案的 worktree | 在裡面有完整自主權；出不去 |
| 2 GitHub | Rulesets、required checks、CODEOWNERS | 只能推 branch；其餘都要過 gate |
| 3 Production | 雲端資源、資料庫 | 無。只有人類打的 release tag 能觸發部署 |

### Zone 1 的規則

**Coding agent 一律在 VM 或雲端執行，不直接跑在 Mac 的使用者帳號下。**

Harness 內建的 sandbox 不足以保護隱私。Claude Code 的 sandbox 預設允許讀取幾乎整個檔案系統，而且只涵蓋 Bash，不涵蓋檔案工具、MCP server 與 hooks；Codex 的 `workspace-write` 也只限制寫入。它們防誤刪有效，防讀取則要靠你把每個路徑都列對。VM 的掛載是預設拒絕：沒掛進去的東西不存在。

本機 sandbox 用的是 Docker Sandboxes（`sandbox/sbx.sh`）。五個性質：

- 每個 agent 一個 microVM，有自己的 kernel。
- **Clone 模式。** Repo 以唯讀方式掛進去，agent 在 VM 內自己的 clone 上工作。它做的任何事都改不到 Mac 上的檔案，交付成果的唯一途徑是 `git push`。這比看起來重要：若是一般的可讀寫掛載，agent 可以在 `.git/hooks` 寫入一個 git hook，等你下次在那個目錄使用 git 時，hook 就會在 Mac 上以你的身分執行。
- 對外連線除了 `sandbox/allowlist.txt` 所列的主機之外一律拒絕，以主機名稱過濾。這同時限制了 prompt injection 之後的資料外送，以及惡意套件的回連。
- VM 內沒有任何 GitHub 憑證。Host 上的 proxy 把佔位值換成你的 agent GitHub App 的一小時 token，token 由 host 上的 helper 在需要時產生。App 的 private key 不離開 host。SSH agent forwarding 會被關掉，因為它預設是開的，會讓 agent 能以你的身分 push。
- 每個被派發的 stage 一個 sandbox，為它建立、結束後移除。Stage 之間不共用檔案、行程或登入狀態，而且各自只拿到它需要的東西（見第 5 節的「角色分配」）。

Lima（`sandbox/vm.sh`）保留作為備援，以及 self-hosted runner 的所在。它在三方面較弱：workspace 是可讀寫掛載、連線以位址而非主機名稱過濾、App 的 key 必須放在 VM 內。兩者都還沒在實機上跑過，見第 9 節。

雲端 session（Claude Code on the web、Codex cloud）是廠商管理的 VM，完全碰不到你的筆電，是隱私上最強的隔離，也是筆電闔上時唯一能繼續工作的地方。環境的網路設為受限，不放任何 secret。

### Mac 上的 hygiene rules

`bin/agentctl doctor` 會檢查其中可以檢查的項目。

- 專案放在 `~/dev` 之類不受 iCloud 同步的位置。iCloud 同步的目錄被誤刪會同步到所有裝置。
- Terminal 與 IDE 不授予 Full Disk Access。這個權限會被在其中執行的任何程式繼承。
- 不對 agent 類的桌面 app 開啟 computer use、螢幕錄製、輔助使用；不在日常使用的瀏覽器 profile 安裝 agent 擴充功能；不把個人的 Gmail、Drive、iCloud 接成 agent 的 connector 或 MCP server。這些路徑繞過 VM 直接碰到私人資料，而且沒有技術手段能強制，只能靠不開啟。
- 開啟 Time Machine 或等效的備份。
- 選配：為開發另建一個 macOS 標準使用者帳號。私人資料在另一個帳號下，檔案權限就擋住了讀取。代價是切換帳號的麻煩。

若一定要在 Mac 上直接跑（例如 IDE 內的短暫互動），`.claude/settings.json` 與 `codex/config.example.toml` 的 host profile 提供了嚴格設定，但這是例外，不是常態。

### Story agent 與維護工作

Agent 在這個 repo 裡有兩種角色，guardrail 對兩者的要求不同。

**Story agent** 由 conductor 派工，無人看管。它不得編輯 guardrail 路徑。這條規則有兩層：硬性的是 CODEOWNERS 與 token 權限；軟性的是 `sandbox/story-agent.claude-settings.json` 裡的 deny rules，安裝在 sandbox 內的使用者層設定與雲端環境，只對 story agent 生效。Product owner 與 planner 同樣由 conductor 派工，但它們必須寫 spec 與 sprint，所以拿到的是 `sandbox/spec-agent.claude-settings.json`：guardrail 路徑仍然不能碰，spec 路徑可以。

**維護工作**是你在 session 裡直接要求 agent 修改 pipeline 本身（workflow、policy、工具、prompt）。這是允許的，條件是由人類當面提出、在 `chore/` branch 上進行、PR 由人類核准。派工的 prompt、issue、檔案內容都不算這種要求。

Repo 共用的 `.claude/settings.json` 因此只放對兩種角色都成立的規則：不讀寫 home、不 force push、不碰雲端 CLI、不自行開 PR 或合併。早期版本把禁止編輯 guardrail 路徑的規則也放在共用設定裡，結果連受你指示的維護工作都被擋住，包括修正這個設定本身。

### 身分與 token

三種身分，權限分開：

| 身分 | 是什麼 | 能做 | 不能做 |
|---|---|---|---|
| 人類 | 專案裡的人，repo admin | 核准 PR、打 release tag、改設定 | 直接 push main（沒有人能） |
| Agent | 每位開發者一個 GitHub App，給他自己的 agent 用 | 推 branch、留言、改 label | 開 PR、核准、merge、改 workflow、打 tag、寫 commit status |
| Conductor | 一個代表 pipeline 的 GitHub App | 開 PR、啟用 auto-merge、派工、通知 | 核准 PR |

為什麼每位開發者的 agent 各用一個 GitHub App：App 的權限就是它被授予的那些，與擁有者的角色無關，所以沒有 admin 的 bypass。它的 token 一小時過期。它不佔座位。而且每人一個，commit 與留言就看得出是誰的 agent 做的；所有人共用一個 App 則看不出來。Personal access token 做不到這些：從 admin 帳號發出的 token，即使是 fine-grained，仍繼承 admin 對 ruleset 的 bypass 資格。`agentctl app-token` 負責產生這個 token，而且是在 host 上執行：sandbox 的 proxy 呼叫它並把結果注入請求，所以 key 與 token 都不在 VM 內。

為什麼 conductor 是另一個 GitHub App：GitHub 不允許作者核准自己的 PR。若雲端 agent 以你的身分開 spec PR，你就無法核准它。所以 agent 只推 branch，由 Conductor App 開 PR。另外，用預設的 `GITHUB_TOKEN` 開的 PR 與做的 merge 不會觸發其他 workflow，gate 根本不會跑。

雲端 session 是例外。Claude Code on the web 與 Codex cloud 透過廠商自己的整合存取 GitHub，以你連結的使用者帳號操作，沒有地方可以換成你自己的 App。這裡的預設是連結你的個人帳號。雲端 agent 因此帶著你的身分，它做不到什麼取決於廠商的限制，以及沒有 bypass 的 ruleset。Red-team checklist 的 E 節測的就是這件事：雲端 agent 能否建立 release tag、能否核准 PR。任一項成功時有兩條路：為雲端服務另外連結一個 machine account，代價是多一個座位；或者不走雲端，所有 stage 都改在 self-hosted runner 上執行（`via = "workflow"`），不花錢但機器必須開著。

## 4. Gate：merge 之前必須成立的事

`main` 的 ruleset（`.github/rulesets/main.json`）沒有 bypass 名單，對人與 agent 一視同仁：

- 禁止直接 push、force push、刪除；只能經 PR 以 squash 合併；branch 必須與 main 同步。
- 五個 required checks 全綠。
- 觸及 CODEOWNERS 所列路徑時，需要 owner（人類）核准；新的 push 會讓舊的核准失效。

| Check | 驗證什麼 | 由誰判定 |
|---|---|---|
| `ci` | lint、全部測試 | 程式 |
| `security` | secret 掃描、靜態分析 | 程式 |
| `spec-verify` | Traceability：每個核准的 test case 都對應到實際執行且通過的測試，已通過的不得消失。Red-green：story 的測試在 main 上會失敗、在 branch 上通過 | 程式 |
| `risk-gate` | 風險分級；T2 需要人類對目前的 commit 核准 | 程式 + 人 |
| `agent-review` | 由另一個 agent 審查實作，並檢查測試是否真的驗到所描述的行為 | Agent |

`spec-verify` 與 `risk-gate` 執行時使用 **base branch 的工具與 policy**，所以一個 PR 無法修改審判自己的規則。`spec-verify` 本身不執行任何 PR 的程式碼：測試在 `ci` job 裡跑，結果以檔案交給 `spec-verify` 判定。

Story 的 PR 以 draft 開啟。Draft 只跑 lint；實作 stage 完成後 conductor 把它轉為可審，完整的 gate 才執行。這是為了節省 Actions 額度，見第 6 節。

### 風險分級

`policy/risk-tiers.toml`：

- **T0** 純文件。Checks 綠即可。
- **T1** 屬於某個已核准 story 的程式變更。Checks 與 agent review 通過即可。
- **T2** 需要人類核准。包括：guardrail 本身（`.github/`、`policy/`、`tools/`、`prompts/` 等）、spec 與 sprint、高風險程式路徑（auth、付款、migration、infra）、任何依賴的新增或變更、超過大小門檻的 diff、不屬於任何 story 的程式變更。

測試檔不算 T0。削弱一個測試就是行為變更。

### 「AI 說會寫 test XYZ，不代表真的寫了」

你核准的 story 裡，每個 test case 有一個 ID（`TC-012-03`）。之後四層檢查，前三層不依賴任何 agent 的說法：

1. **Traceability。** 測試名稱必須帶 TC ID。CI 讀測試執行器輸出的 JUnit XML，確認每個 ID 都有至少一個實際執行且通過的測試。被 skip 的、不存在的、只寫在註解裡的都不算。依據是執行結果，不是搜尋原始碼。
2. **Red-green。** 把 PR 的測試檔疊到 main 上執行，必須失敗；在 PR 上必須通過。`assert True` 這種空測試在 main 上就會通過，因而被擋下。
3. **不得消失。** 在 main 上通過的 TC，之後不能不見。Spec 本身受 CODEOWNERS 保護，agent 不能悄悄刪掉一條 TC。
4. **測試有效性的稽核。** 審查 agent（不同於寫測試與寫實作的 agent）對每個 TC 逐條判斷：測試的斷言是否真的驗證了描述的行為。這層補的是前三層看不到的情況：測試存在、會紅會綠，但驗的是錯的東西。

前三層由 `spec-verify` 這一個 check 執行。

Merge 之後，`evidence` workflow 把「AC → TC → 測試 → 結果」的對照表貼到 story 的 issue 上。你看這張表，不用讀程式。

這套保證的邊界有兩個。第一，它確保你核准的每個 TC 都有一個會隨行為改變的測試在跑，但不保證 TC 清單本身完整；清單的完整性取決於 PO 的提問與你核准 story 時的審閱。第二，測試結果是由 PR 的程式碼產生的，agent 有能力直接寫出假的結果檔。這沒有硬性的防線，靠的是 `Makefile` 受保護、審查 agent 與每週抽查。

### `agent-review` 的強度

這是五個 check 裡唯一由 agent 判定的，強度也最弱，要誠實說明。

Claude 的 review 以 workflow job 的形式執行，由 job 自己寫入 status，實作 agent 的 token 沒有這個權限，所以無法偽造。Codex 的 review 來自它的 GitHub 整合，由 `bridge` job 轉成 status。若 review 改在一般的雲端 session 中進行，審查者與實作者可能是同一個 GitHub 身分，這時無法從身分上區分兩者。

因此設計上不讓任何硬性保證依賴 `agent-review`。高風險變更有人類核准，測試的存在與有效性有機械檢查。Agent review 提供的是語意層的把關，錯放的代價由其他 gate 限制。

## 5. 從一行字到 production

```
Stage 0  你說一句話（PO chat，或寫進 roadmap）
Stage 1  PO agent 產出 story                    → 你核准 spec PR        【Gate 1】
Stage 2  design   設計 agent 寫設計文件
Stage 3  tests    測試 agent 只根據 story 寫測試（此時必須是紅的）
Stage 4  impl     實作 agent 讓測試變綠
Stage 5  review   審查 agent 審實作並稽核測試
Stage 6  五個 check 全綠 → auto-merge → evidence 表貼到 issue
Stage 7  你打 v* tag → 部署 production                                   【Gate 2】
```

每個 stage 是一個全新的 agent session，沒有前一個 session 的記憶。它需要的一切都在 spec、story issue、branch 與 commit 歷史裡。指令在 `prompts/`，與廠商無關。

### AI Product Owner

你的需求通常是一句話。PO（`prompts/product-owner.md`）把它變成你能在兩分鐘內核准的 story。

- 它先讀 `docs/product/` 的領域文件與相關的既有 story，檢查新需求是否與既有行為衝突。
- 最多問五個問題，而且只問「會改變要做什麼、且事後難以反悔」的：金流與訂單狀態、失敗與退回之後怎麼辦、誰有權限、資料保存與對外通知。其餘自行決定並列為假設。
- 產出三個檔案：`story.md`（英文，agent 實作與審查的依據）、`story-zh-TW.md`（繁中，你閱讀與核准的版本）、`spec.toml`（機器讀的）。兩份 story 各限 80 行。範例見 `docs/specs/000-example/`，就是「轉帳付款附憑證」那句話的結果。

你核准的是中文、agent 讀的是英文，兩者的語意落差是雙語 story 的主要風險。分三層處理：`spec-lint` 檢查兩份的 AC 與 TC ID 相同且順序一致、章節相同；CI 檢查兩份必須在同一個 PR 一起變更；PO 寫完後逐條自我比對，另一家廠商的 review agent 再逐條比對一次，語意差異視為 blocking。前兩層是機械檢查，第三層是 agent 的判斷，不是硬性保證。兩份不一致時以英文版為準，因為那是實際被實作的版本。

兩種模式：**chat**，你在手機或桌面上與它對話，適合想深入討論的需求；**async**，你只在 `docs/product/roadmap.md` 加一行，conductor 會派 PO 起草 spec PR，問題寫在 PR 描述裡，你用 review comment 回答。你回來時面對的是可以直接核准或簡短回覆的 spec。未核准的 spec PR 上限是三個，避免堆積。

核准的方式是在 GitHub approve 那個 PR，手機 app 即可。不用 label 當核准訊號，因為 agent 能改 label。

### 角色分配

`policy/roles.toml` 按開發者設定每個 stage 用哪個 harness，並有 fallback 順序。原則是讓審查者與實作者不同廠商。

實際的限制是額度。實作是最耗 token 的 stage，審查最輕，所以把實作放在一個人較大的訂閱上，審查放在較小的那個。三種常見的組態：

| 組態 | 誰來審查 | 放棄了什麼 |
|---|---|---|
| 一人、單一廠商 | 同一個 harness 的全新 session | 跨廠商審查。機械檢查承擔主要保證 |
| 一人、多廠商 | 與實作者不同的廠商 | 無，只要兩邊額度都夠 |
| 多人、各自不同的 AI | 視每個人自己有哪些而定 | 只有一種廠商的人，他名下的 story 是同廠商審查 |

不論哪種組態，T2 變更都仍然交給人類。只有一個人時，那個人同時也是 director。升級方案後改設定即可。

把角色分到不同的 session 還不夠，如果每個 session 握有的權力都一樣的話。所以每個 stage 的 sandbox 只拿到該 stage 需要的東西：

| Stage | 它的 GitHub token 能做的事 | 網路 | 可以編輯 |
|---|---|---|---|
| design、tests、impl（以及它的 fix 與解衝突） | 推 branch；留言、改 label | 原始碼託管、模型供應商、套件 registry | 程式與測試；不含 guardrail 與已核准的 spec |
| review、triage | 讀 repo；留言、改 label、送出 review。**不能 push** | 只有原始碼託管與模型供應商 | 反正它也交付不了任何東西 |
| product-owner、planner | 推 branch；留言、改 label | 只有原始碼託管與模型供應商 | Spec、sprint、產品文件；不含 guardrail |

前兩欄是硬性控制。GitHub 產生 App token 時可以只給 App 權限的子集，sandbox 的網路 policy 也是逐個 sandbox 設定的，所以負責審查的 agent 若嘗試 push，會被 GitHub 拒絕，不管它的 prompt 或它自己怎麼推論。第三欄是 harness 的 deny rules，屬於軟性的一層。這張表以常數的形式寫在 `tools/agentctl/profiles.py`，而且建立 sandbox 時用的是固定在 repo 之外的副本，所以一個 branch 無法替自己加權限。

兩個限制。GitHub 的權限是以 repo 為單位，不是以路徑為單位：「寫測試的不能碰實作」與「寫實作的不能削弱測試」無法用 token 表達，仍然交給 `spec-verify`、CODEOWNERS 與 review。另外，這種區隔只存在於 Docker Sandboxes 這條路徑。Lima 備援是所有 stage 共用的一個長駐 VM；雲端 session 則不論哪個 stage，都以你連結的帳號操作。

## 6. 持續運轉：Conductor

你不在的時候，是 conductor 在推動工作。

### 它是什麼

一支沒有狀態、不含 LLM 的程式（`agentctl reconcile`）。它可以跑在你 Mac 的 terminal，也可以跑在 GitHub Actions 上。每次執行都讀出完整的現況：sprint、spec、issue、PR、check 結果，算出現在該發生的下一件事，然後去做。它自己不記任何東西；所有記憶都在 GitHub 上（label、issue 關聯、隱藏的 marker 留言）。因此中斷、重跑、漏掉事件都無妨，下一次執行會得到同樣的結論。

### Conductor 在哪裡跑

Conductor 是決定性的程式，不是 agent，所以在你的 Mac 上直接執行是安全的，而且不耗 Actions 額度。

- **你在電腦前**：`bin/agentctl conductor here`。它每三分鐘輪詢一次，每次都從 `origin/main` 讀取核准的 sprint、spec 與 policy，不讀你工作目錄裡的內容。
- **你要外出**：`bin/agentctl conductor away`，或直接按 Ctrl-C。交給 GitHub Actions。
- **你忘了交接就闔上筆電**：本機 conductor 每次執行都會更新一個 lease。Actions 每四小時的排程執行會檢查它，超過 20 分鐘沒更新就自動接手。

兩個 repo variable 確保同一時間只有一邊在動作：`CONDUCTOR_HOME`（`local` 或 `actions`）與 `CONDUCTOR_LEASE`。本機持有 lease 期間，Actions 上由事件觸發的執行會被跳過，不耗分鐘。

在 Actions 上，事件是主要驅動（`ci` 完成、PR 關閉、review 送出、issue 的 label 變更），排程只負責抓停滯與漏接。本機執行時用的是你自己的 `gh` 登入；派工需要的觸發網址與 token 放在 `.env.conductor`（已列入 `.gitignore`）。

### 順序的判斷從哪裡來

一支程式無法判斷 story 該先做哪個。它也不需要，因為判斷發生在別處：

**規劃時，由 agent 判斷，你核准。** Planner（`prompts/planner.md`）讀所有候選 story 與程式碼，為每個 story 確定 `depends_on`（必須先合併的 story）、`touches`（會動到的模組與共用資源）、`priority`。這些寫在 `spec.toml` 裡，隨 sprint PR 給你核准。你核准的是範圍與優先序。

**執行時，由程式計算。** 一個 story 可以開工的條件：相依的 story 都已合併、沒有被標為 blocked、它的 `touches` 與進行中的 story 沒有交集、未超過同時進行的上限。符合條件的依 priority、能解鎖的下游數量、編號排序。同樣的輸入永遠得到同樣的結果，不耗額度，可以完整地單元測試。

**出狀況時，由一個短命的 triage session 判斷。** 規劃出來的相依關係會有錯，常見的是做到一半才發現需要另一個還沒完成的 story。Conductor 偵測到 stage 反覆失敗或停滯時，啟動 triage agent（`prompts/triage.md`）。它只能做三件事：追加一條「blocked by」關聯、要求重試並說明該怎麼做不同、或升級給你並附上選項。它不能改 spec、不能改 sprint 範圍、不能動程式或測試。

### 為什麼不掛一個長時間的 LLM session 來監督

長 session 的狀態在它的 context 裡。Context 會被壓縮而遺失指示，session 中斷後無法完整恢復，行為難以稽核，而且持續消耗額度。把狀態放在 GitHub、每次判斷都用全新的 context，這些問題不存在。

現有工具的經驗指向同一邊。以 LLM 擔任協調者的 Gas Town，作者表示它在模型升級後失效，agent 轉而不斷修改 harness 本身（這項來自二手報導）。Claude Code 的 agent teams 文件記載 lead 會提早結束、任務狀態落後而卡住下游。Anthropic 關於 long-running agent 的工程文章主張每個 session 從全新 context 開始，連續性放在檔案與 git。最接近本設計的是 OpenAI Symphony：決定性的 reconcile 迴圈，以 issue tracker 為事實來源；它只支援 Codex 與 Linear，所以這裡採用它的做法而非它的實作。

### 會做與不會做的事

- 某個 story 在等你時，繞過它做別的。等你的 story 不佔同時進行的名額。
- Sprint 裡所有未完成的 story 都卡在你身上時，全部停下，通知你一次。
- Sprint 完成、下一個尚未核准時，開發停止。只有 spec 的起草繼續。它不會自行擴張範圍。
- PR 落後 main 時更新 branch；有衝突時派解衝突的任務。
- main 變紅時停止派發，只派一個修復任務。
- 某個 harness 額度用盡時改用 fallback，都用盡就等待。
- 所有 gate 通過後啟用 auto-merge，但只限 `policy/conductor.toml` 的 `auto_merge_tiers` 所列的分級。

### Fuses

- **Kill switch**：把 repo variable `CONDUCTOR_PAUSED` 設為 `true`，下一次執行起停止一切派發。
- 上限：同時進行的 story 數、每日開啟的 PR 數、同一 stage 的重試次數、fix 與 review 的來回輪數、triage 次數。超過就升級給你，不會無限重試。

### Actions 額度

GitHub 以金額計算額度，Team 方案每月 $18。標準 Linux runner 每分鐘 $0.006（約 3,000 分鐘），1-core 的 Linux runner 每分鐘 $0.002，self-hosted runner 不計費。**每個 job 的時間無條件進位到整分鐘**，所以一個跑 5 秒的 job 也算一分鐘。這條規則決定了下面的設計。

- 測試套件每次只跑必要的次數：head 一次，story branch 再加上 base 疊測試檔的一次，兩者在同一個 job 裡。
- Draft PR 只跑 lint。完整的 gate 留到實作完成，每個 story 約三次而不是每次 push 一次。
- Agent 每個 stage 結束才 push 一次。
- 不執行 PR 程式碼的輕量 job（`spec-verify`、`risk-gate`、conductor、evidence、brief）可以改用 1-core runner，以 repo variable `LIGHT_RUNNER` 設定。
- Conductor 在 Actions 上的心跳是每四小時一次；你在電腦前時它根本不在 Actions 上跑。

| | 第一版 | 現在 |
|---|---|---|
| 每次完整 gate | 約 5T + 7 分鐘 | 約 2T + 4 分鐘，加約 3 個輕量 job |
| 每個 story 的完整 gate 次數 | 約 8 | 約 3 |
| 每個 story（T=3） | 約 215 分鐘 | 約 55 分鐘等值 |
| 每月固定開銷 | 約 750 分鐘 | 約 70 分鐘等值，本機執行 conductor 時更低 |
| 每月可支撐的 story（T=3 / T=10） | 約 10 / 4 | 約 50 / 30 |

T 是測試套件跑一次的分鐘數；「等值」是把 1-core runner 的分鐘按單價折算。**這些都是估算，還沒有實測。** Runbook 的 spike 會要你記下實際數字。

**overflow 到 self-hosted。** `agentctl budget` 從 Actions 的 job 紀錄估算當月用量（每日的 brief 與 conductor 的排程執行都會跑）。達到額度的 85% 時，它把 repo variable `CI_RUNNER` 改指向你 Mac 上 VM 內的 runner，新的月份開始時改回來。門檻、單價、額度都在 `policy/conductor.toml`。

只有 `ci` 與 `security` 會移過去，因為它們是執行 PR 程式碼的重型 job。負責判定的 job 永遠留在 GitHub-hosted runner：self-hosted runner 不會在每個 job 之間重建，被 PR 程式碼碰過的機器不能拿來判定它自己。overflow 期間若 Mac 闔上，這兩個 check 會排隊，conductor 把它們視為進行中而等待。

### Agent 在哪裡跑

| 位置 | 如何啟動 | 筆電要開著嗎 |
|---|---|---|
| Claude Code 雲端 session | Conductor 呼叫 scheduled task 的 API trigger | 否 |
| Codex cloud | Conductor 在 PR 或 issue 上留 `@codex` | 否 |
| Claude review | `agent-review` workflow job | 否 |
| 本機的 Docker Sandbox（clone 模式） | 在你 Mac 上執行的 conductor 直接啟動 | 是 |
| Lima VM 內的 self-hosted runner | Conductor 啟動 `agent-job` workflow，runner 上線時領取 | 是 |

前三者是主力。後兩個是補充產能與備援，需要 Mac 開著；Ollama 的任務只能走它們。Conductor 在 GitHub Actions 上時，派給本機 sandbox 的 stage 會等到 conductor 回到 Mac 上執行才開始。哪條雲端路徑實際可行，要由 spike 確認；不可行的在 `policy/roles.toml` 改成 `via = "sbx"`。

## 7. 你的日常

你做四件事：

1. 在 roadmap 加一行，或跟 PO 說一句話。
2. 核准或回覆 spec PR。
3. 核准 sprint PR。
4. 打 release tag。

你看兩個地方：

- **Director's brief**：一個固定的 issue，每天更新。內容是 sprint 進度、等你決定的事、被卡住的項目、新合併的項目，以及當月 Actions 用量的估算與 conductor 目前在哪裡跑。每週一多一段稽核：各分級的合併數、revert 數、升級次數，以及隨機抽出的幾個未經人類合併的 PR 供你抽查。數字來自 GitHub，不來自 agent 的自述。
- **GitHub 的通知**：要你 review 的 PR 與 assign 給你的 issue，就是等你決定的事項清單。

## 8. 分階段開啟自動合併

新專案的測試還不足以當作合併的依據，所以 `auto_merge_tiers` 預設是空的（shadow mode）：所有 gate 照常計算與回報，但由你按 merge，conductor 只通知你「這個可以合併了」。

觀察一段時間，確認 gate 的結論與你自己的判斷一致之後，先開 `T0`，再開 `T1`。T2 永遠需要人類核准。

自動合併的可信度上限是測試的品質。這是分階段的理由。

## 9. 已驗證與未驗證

**已在開發時驗證：**

- `agentctl` 的風險分級、雙語 spec 與文件檢查、traceability、red-green 判定、conductor 排程邏輯、額度估算、lease 判定，共 96 個單元測試。
- Red-green 在一個真實的 git repo 上端對端執行，分成收集與判定兩步：空測試被擋下，改成真的測試後通過；沒有執行收集步驟時判定為失敗而非通過。
- Conductor 的 GitHub 介接層對模擬的 `gh` 執行過：派工、留 marker、把 draft 轉為可審、單一動作失敗不影響其他動作；lease 有效時 Actions 端不動作、過期時接手；用量達門檻時改寫 `CI_RUNNER`。
- Workflow 通過 actionlint，shell script 通過 shellcheck，指令攔截 hook 有測試。

**尚未驗證，需要在你的帳號與機器上做（runbook 的 spike 與 red-team checklist）：**

- Conductor 對真實 GitHub API 的行為，特別是 issue 相依關聯的 API 與 check 狀態的讀取。
- 以 API 觸發 Claude 雲端 scheduled task 的實際介面，以及以 `@codex` 留言啟動任意任務是否可行、對留言者身分有何要求。
- 連結個人 admin 帳號的雲端 session 在 GitHub 上實際能做到什麼（red-team checklist 的 E 節）。
- 對真實 API 產生 agent App 的 token（`agentctl app-token`）。
- `anthropics/claude-code-action` 目前的輸入參數；Codex review bot 的帳號名稱與 review 格式。
- 實機上的 Docker Sandboxes：`sandbox/sbx.sh` 用到的 `sbx` 指令、clone 模式、proxy 是否會把 App token 注入走 HTTPS 的 `git push`（文件沒有明講）、sandbox 內 home 目錄的路徑、各 harness 的無人值守執行方式。
- 透過真實 API 把 App token 縮小到較少的權限，以及逐個 sandbox 的網路規則：兩者都依文件撰寫，都還沒實際跑過。
- `sandbox/` 下的 Lima 設定與 egress 規則。
- `.claude/settings.json` 的 sandbox 與 permission 語法是否符合目前版本。
- 1-core runner 的實際 label；`workflow_run` 觸發 conductor 與跨 workflow 下載 artifact 所需的權限；Conductor App 寫入 repo variable 的權限。
- Draft PR 上被跳過的 required check 在轉為可審之後的行為。
- 額度估算與 GitHub 帳單的實際差距；Actions jobs API 回傳的 runner label 是否足以區分三類 runner。
- 本機 conductor（`conductor here`）在真實 repo 上的行為。
- GitHub Team 方案在 private repo 上的功能邊界：ruleset 與 auto-merge 可用，merge queue 與 environment 的 required reviewers 不可用。後者是 release 改用 tag 保護的原因。

## 10. 已知限制

- 兩位開發者本身被信任。設計防的是 agent 失控與 prompt injection，不防內部人員。
- Clone 模式下，agent 的工作在 push 之前只存在於 VM 內。沒有 push 就結束的 stage，除了 log 之外什麼都不會留下。
- 在 Lima 備援與 sbx 的直接掛載模式下，workspace 是可讀寫的。Agent 因此可以毀掉工作目錄，也可以埋一個之後會在 Mac 上執行的 git hook。這是預設採用 clone 模式的原因。
- Docker Sandboxes 的版本號是 0.x，指令可能變動。
- 依 stage 區分的權限只存在於 Docker Sandboxes 這條路徑。Lima 備援中所有 stage 共用一個 VM 與一個可寫入的 token；雲端 session 中每個 stage 都以你連結的帳號操作。
- VM 內的訂閱登入狀態理論上可被惡意的 repo 內容竊取。Egress allowlist 降低但不消除這個風險。
- 在 Lima 備援中，egress 規則以位址過濾，與允許的主機共用位址的其他主機也連得到。
- 雲端 session 以你連結的個人帳號操作。在跑過 red-team checklist 的 E 節之前，應假設雲端 agent 在 GitHub 上能做到該帳號能做的一切，只受沒有 bypass 的 ruleset 限制。Release tag 的 ruleset 允許 admin bypass，所以它是必測項目之一。
- 你貼進 PO chat 或 issue 的內容會進入廠商的 context，不在隔離範圍內。
- 雙語 story 的語意一致性沒有硬性保證。你核准的中文與 agent 實作的英文若有出入，只有 review agent 與你自己能發現。
- 測試結果由 PR 的程式碼產生，可以被偽造。見第 4 節。
- Actions 用量是估算。它可能與帳單有出入，overflow 的時機因此可能偏早或偏晚。
- `touches` 是預測，會漏判。代價是合併衝突與重工，由 triage 事後修正；不會導致錯誤的程式被合併。
- 持續運轉的產能受訂閱額度限制。額度用盡時工作會變慢，不會失敗。
- 雲端觸發依賴兩家仍在演進的功能。退路是 self-hosted runner，但它需要 Mac 開機。
- 你不在時，等你決定的事會累積。這是 director 模式下唯一由你決定的節奏。
