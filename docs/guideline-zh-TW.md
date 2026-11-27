# AI Coding Agent 開發 Kit 的 Guideline

*English: [guideline.md](guideline.md)。兩份內容不一致時以英文版為準。*

本文件說明這個 kit 的設計：為什麼這樣建構、各部分如何配合、哪些已驗證而哪些尚未驗證。它不含設定步驟。每個 layer 都有自己的設定文件與 checklist：[layer 1，isolation](layer-1-isolation-zh-TW.md)、[layer 2，GitHub protection](layer-2-github-zh-TW.md)、[layer 3，CI gates](layer-3-ci-zh-TW.md) 與 [layer 4，conductor](layer-4-conductor-zh-TW.md)。在專案中採用這個 kit，見 [adopting-zh-TW.md](adopting-zh-TW.md)。威脅以及對應的控制措施見 [threat-model-zh-TW.md](threat-model-zh-TW.md)。

## 1. 目標

1. **Agent 碰不到你的私人資料，也無法造成不可復原的損害。** 依嚴重程度排序：讀取私人檔案（一旦讀取就無法收回）、誤刪工作目錄以外的檔案、使用機器上暫時有效的雲端憑證，以及未來的 production。
2. **人的注意力是瓶頸。** 你是 director：你決定要建構什麼、核准範圍、並發布到 production。你不必閱讀一般的 pull request、不必 merge，也不必派工。

這個 kit 對團隊沒有任何固定的假設。一個人加一份 AI 訂閱就夠了；一個人有多份訂閱，或幾個人各自帶自己的訂閱，也都可以。誰可以核准產品決策、每個人的哪個 harness 負責哪個 stage，都是 `agentdev.toml`（`[roles]`）中的設定，CODEOWNERS 也由同一個檔案產生。只有兩件事是固定的：agent 以訂閱方案執行，不使用隨用隨付的 API key；以及 repository 所在的 GitHub 方案要能對私有 repository 強制執行 ruleset。

## 2. 三項原則

**用能力邊界來保護，不靠 agent 的自律。** Prompt、權限設定與指令黑名單都可能被繞過，所以只算第二道防線。真正的保證是：在 agent 執行的環境中，不存在任何能造成損害的東西。它看不到你的 home 目錄，它持有的 token 也沒有危險的權限。

**GitHub 是唯一的控制平面。** 所有 harness 只透過 branch、pull request 與 issue 交接工作。更換模型、更換廠商或加入本地模型，都不會改變流程。這也是不需要 API key 的原因：每家廠商的模型都在它自己的 harness 中，使用訂閱額度執行。

**機械式的檢查優先於 agent 對自己的說法。** Agent 會過早宣稱完成，也會高估自己的產出。任何能由程式驗證的事（測試是否真的存在並執行、是否真的演練了該行為），都不去問 agent。

## 3. Kit、它的 layer 與它的設定

### 四個 layer

| Layer | 關注點 | 主要部分 |
|---|---|---|
| 1. Isolation | Agent 碰不到 Mac，也拿不到強大的憑證 | clone 模式的 Docker Sandboxes (sbx)、每位開發者專屬、給 agent 用的 GitHub App、Mac 的安全習慣、雲端 session |
| 2. GitHub protection | Agent 無法更改用來評判它的東西，也無法 merge 或 release | Ruleset（`templates/rulesets/`，由 `agentctl rulesets 2` 套用）、由 `agentdev.toml` 產生的 CODEOWNERS、`conductor` environment、Conductor GitHub App |
| 3. CI gates | 沒有證據就不能 merge | Reusable workflow `ci`、`security`、`spec-verify`、`risk-gate`、`agent-review` |
| 4. Conductor | 不需要你，工作也會往前推進 | `agentctl conductor`：把 stage 派給 agent、開啟 pull request，並在你允許之後 merge |

每個 layer 都可以單獨採用，但它們彼此依賴。Layer 2 可以單獨採用。Layer 3 的強度只有 layer 2 那麼高：agent 能編輯或略過的 check 什麼也證明不了。Layer 4 需要 layer 1 的身分與 layer 2 的 ruleset，它的 merge 也只能和 layer 3 的 gate 一樣可靠。對既有專案，順序是先 1 和 2，再 3，最後以 shadow mode 採用 4（第 9 節）。

### 每台 Mac 安裝一次，每個專案固定版本

Kit 在主機端的程式碼以你的權限在 Mac 上執行，而 agent 可以更改專案目錄樹中的任何東西。所以那些程式碼絕不放在專案目錄樹中。

- `install.sh [REF]` 在 kit 的 clone 中執行，以完整 commit SHA 把某個版本解開到 `~/.local/share/agent-dev-kit/versions/<sha>/`，設為唯讀，並把 `agentctl` launcher 放進 `~/.local/bin`。
- Launcher 執行專案在 `agentdev.toml`（`[kit] version`）中固定的版本，該設定讀自專案的**預設 branch**（`origin/HEAD`，以最後一次 fetch 為準），絕不讀工作目錄。Branch（包括 agent 的 branch）無法選擇在 Mac 上執行哪一份程式碼。`AGENTDEV_KIT_VERSION` 會覆寫這個 pin，用於專案之外，或在 pin 尚未進入預設 branch 的導入階段。
- Launcher 以 `python3 -I` 啟動工具，使目前目錄與 `PYTHONPATH` 都不在 import 路徑上，所以 checkout 中名為 `json.py` 的檔案無法取代真正的模組。

結果是：沒有「這個 checkout 是否可信」的檢查，沒有每個專案各自一份的工具，也沒有禁止執行 agent branch 上的主機端腳本的規則。Agent 無法更改的程式碼，不需要這些。

CI 中也是如此。每個 reusable workflow 都接受 `kit_version`，從 codeload 把該 SHA 的 kit 抓到 runner 的暫存目錄中，並從那裡執行。專案的 caller workflow（`agentdev-*.yml`）會兩次寫出這個 SHA，一次在 `uses: ...@<sha>`，一次在 `kit_version: <sha>`。在 `ci` 的 lint 步驟中執行的 `agentctl pins`，除非兩者都等於 `[kit] version`，否則會失敗。要升級，請在同一個 pull request 中修改 `agentdev.toml` 與每一個 caller 中的 SHA（這是 T2 變更），並在每台 Mac 上執行 `./install.sh <sha>`。

### 一份設定檔

專案根目錄的 `agentdev.toml` 持有所有專案設定，疊加在 kit 的預設值之上（`tools/agentctl/defaults.toml`，是每個 key 的參考）。Table 逐 key 合併；其他任何值（包括 list）都會整個取代預設值。`agentctl config KEY` 會印出一項設定。

| 區段 | 內容 |
|---|---|
| `[kit]` | 固定的版本與 kit 的 repository |
| `[paths]` | Spec、sprint、roadmap、產品文件與設計筆記所在的位置 |
| `[stories]` | `id_digits`（預設 3）、`translation`（預設 `zh-TW`，`""` 表示不使用）、`max_lines` |
| `[docs]` | 文件的翻譯配對，以及哪些必須存在 |
| `[tests]` | `setup_cmd`、`lint_cmd`、`test_cmd`、`junit_glob`、`test_paths`：與專案技術堆疊之間的契約 |
| `[risk.thresholds]`、`[risk.t0]`、`[risk.t2]` | 風險等級（第 6 節） |
| `[conductor]` | 上限、fuse、`auto_merge_tiers`、stage 逾時、Actions 預算 |
| `[roles]` | Director、human、planner、每個 harness 如何啟動、哪個 harness 為誰負責哪個 stage |

`.github/**` 與 `agentdev.toml` 一律是 guardrail，不論專案怎麼寫。T2 永遠不能列入 `auto_merge_tiers`。對這個檔案的變更是 T2，所以 agent 無法放寬自己的限制。Stage 的 prompt 屬於 kit（`prompts/`）；它們是由這個檔案填入內容的範本（`agentctl prompt STAGE`），conductor 在每次派工時送出完整渲染後的 prompt，所以專案不需要任何 prompt 檔案。

## 4. 信任區

| 區域 | 內容 | Agent 能做什麼 |
|---|---|---|
| 0 你的 Mac | 私人資料、瀏覽器、Keychain、暫時有效的雲端 token、已安裝的 kit、Ollama | Coding agent 不在這裡執行 |
| 1 Sandbox | 本地 microVM，或廠商的雲端 session。專案的 repository 以唯讀方式掛載，內部有一份私有的 clone | 內部完全自主；出不去 |
| 2 GitHub | Ruleset、必要的 check、CODEOWNERS | 只能 push branch。無法開啟或 merge pull request；其他一切都必須通過 gate |
| 3 Production | 雲端資源、資料庫 | 什麼都不能做。只有人 push 的 release tag 才能觸發部署 |

### 區域 1 的規則

**Coding agent 一律在 microVM 或雲端中執行，絕不直接在 Mac 的使用者帳號下執行。**

Harness 內建的 sandbox 不足以保護隱私。Claude Code 的 sandbox 預設允許讀取幾乎整個檔案系統，而且它只涵蓋 Bash，不涵蓋檔案工具、MCP server 或 hook。Codex 的 `workspace-write` 同樣只限制寫入。它們可以防止意外刪除，但防止讀取要靠你把每個路徑都正確列出。microVM 的掛載預設是拒絕：沒有掛載的東西就不存在。

本地 sandbox 是 Docker Sandboxes（`sandbox/sbx.sh`，透過 `agentctl sandbox` 執行）。它是唯一支援的本地 runtime。它的特性：

- **每個 agent 一個 microVM**，有自己的 kernel。
- **Clone 模式。** Repository 以唯讀方式掛載，agent 在 VM 內的私有 clone 上工作。它做的任何事都不會更改 Mac 上的任何檔案，它交付工作的唯一方式是 `git push`。這比看起來重要得多。若是一般的可讀寫掛載，agent 可以把 git hook 寫進 `.git/hooks`，之後你下次在該目錄使用 git 時，那個 hook 就會以你的身分在 Mac 上執行。掛載的是整個 repository 目錄，包括未追蹤與被忽略的檔案，所以專案目錄中不得存放任何機密。當腳本發現有未追蹤的檔案，其檔名看起來像機密時，會拒絕啟動 sandbox。那項檢查只看檔名，所以它是提醒，不是保證。
- **對外連線一律拒絕，只有 allowlist 上的主機例外**，依主機名稱過濾：sbx 的 deny-all preset 加上 `sandbox/allowlist.txt`，而 `sandbox/allowlist-build.txt` 的套件 registry 只提供給需要 build 的 stage。這份 allowlist 同時限制 prompt injection 之後的資料外洩，以及惡意套件的回呼。由於這個 preset 是整台機器共用的，可以在腳本之外被更改，所以每個 sandbox 在建立時也會從內部做探測：GitHub 必須連得到，而兩個不在 allowlist 上的主機必須連不到。這是當下對三個主機的抽查。它無法區分政策拒絕與來源伺服器自己回的 403 或 5xx，也不能證明實際生效的 allowlist 等於專案的清單。
- **VM 內沒有 GitHub 憑證。** 主機上的 proxy 把一個 placeholder 換成開發者之 agent GitHub App 的一小時 token，該 token 由主機上的 helper 在需要時產生。App 的私鑰不會離開主機。SSH agent forwarding 已關閉，因為它預設是開啟的，會讓 agent 以你的身分 push。共用的 skills store 也已關閉，因為預設它會以唯讀方式掛載進每個 sandbox。
- **每個被派出的 stage 一個 sandbox，絕不重複使用**，不論工作如何結束都會移除。各 stage 不共用檔案、行程或登入狀態，每個 stage 只拿到它需要的東西（第 7 節，「角色分配」）。
- **專案目錄中的任何東西都不會在主機上執行。** Sandbox 腳本是已安裝 kit 自己的，而它們從專案讀取的內容（`agentdev.toml`）來自預設 branch。Story id、stage 與 harness 在進入路徑、sandbox 名稱或指令之前都會先驗證。

沒有互動模式。若要自己與 agent 一起工作，請直接使用 sbx（`sbx create --clone`、`sbx run`）。這樣的 sandbox 會得到 `agentctl sandbox setup` 設定的整機 deny-all preset 與 allowlist，但沒有 GitHub token，也沒有 harness 的 deny 規則。

**雲端 session**（Claude Code on the web、Codex cloud）是廠商管理的 VM，完全碰不到你的筆電。它們是隱私方面最強的隔離，也是在筆電闔上時唯一能繼續工作的地方。請把 environment 的網路設為 restricted，且不要在其中放任何機密。

### Mac 上的安全習慣規則

`agentctl doctor` 會檢查以下可以被檢查的項目。

- 把專案放在不被 iCloud 同步的地方，例如 `~/dev`。在同步目錄中意外刪除的東西會同步到每一台裝置。
- 專案目錄中不放任何機密：不要有 `.env` 檔案、金鑰或憑證，被忽略的也不行。Clone 模式的 sandbox 能讀取整個目錄。因此 conductor 的憑證放在 `~/.config/agent-dev/<owner>-<repo>/conductor.env`，agent App 的金鑰放在 `~/.config/agent-app/`，都在 repository 之外。
- 不要授予終端機或 IDE「完整磁碟取用權限」（Full Disk Access）。在其中執行的任何程式都會繼承該權限。
- 不要對 agent 類的桌面應用程式啟用 computer use、螢幕錄製或輔助使用。不要在你日常使用的瀏覽器 profile 中安裝 agent 擴充功能。不要把個人的 Gmail、Drive 或 iCloud 接成 agent 的 connector 或 MCP server。這些途徑繞過 VM，直接觸及私人資料，而且沒有技術手段可以強制執行這條規則。它只能靠不開啟來維持。
- 開啟 Time Machine 或同等的備份。
- 選用：為開發另外建立一個標準的 macOS 使用者帳號。私人資料放在另一個帳號之下，檔案權限就會擋住讀取。代價是切換帳號的麻煩。

如果你真的必須直接在 Mac 上執行 agent（例如在 IDE 內做一次簡短的互動），專案的 `.claude/settings.json` 與 `sandbox/codex-config.example.toml` 提供了嚴格的設定。這是例外，不是常態。

### Story agent 與維護工作

Agent 在專案中有兩種角色，guardrail 對兩者的要求不同。

**Story agent** 由 conductor 派出，無人看管地執行。它不得編輯 guardrail 路徑。硬性的一層是 CODEOWNERS、ruleset 與 token 權限。軟性的一層是 harness 的 deny 規則，由 `[risk.t2]` 為每個 sandbox 產生（`agentctl harness-settings story|spec`），安裝在 sandbox 與雲端 environment 中。Product owner 與 planner 以同樣方式派出，但必須撰寫 spec 與 sprint，所以它們的規則對 spec 路徑開放，對 guardrail 路徑關閉。

**維護工作**是指你直接在 session 中要求 agent 去更改 pipeline 本身（workflow、`agentdev.toml`、agent 設定）。在以下條件下允許：由人當面要求、工作在 `chore/` branch 上進行、並由人核准該 pull request。Dispatch prompt、issue 或檔案內容都不算這樣的要求。Conductor 會為 `chore/` branch 開啟 pull request，狀態為 ready for review。由人核准並 merge；conductor 不會對它啟用 auto-merge。

專案共用的 `.claude/settings.json` 只放對兩種角色都成立的規則：不得在 home 中讀取或寫入、不得 force push、不得使用雲端 CLI、不得自行開啟或 merge pull request。若把禁止編輯 guardrail 的規則放在那裡，連你要求的維護工作也會被擋下。

## 5. 身分與 token

三種身分，權限各自獨立：

| 身分 | 它是什麼 | 可以 | 不可以 |
|---|---|---|---|
| Human | 專案上的人、repository admin | 核准 pull request、merge、push release tag、更改設定 | 直接 push 到 main（沒有人可以）；略過 check 或核准 |
| Agent | 每位開發者一個 GitHub App，供該開發者的 agent 使用 | Push branch、留言、更改 label。Review token 可以 review pull request，但不能 push | Merge、以 code owner 身分核准、更改 workflow、建立 tag、寫入 commit status。用來 push 的 token 不能開啟、重新指定目標或 review pull request |
| Conductor | Pipeline 專用的一個 GitHub App | 開啟 pull request、標記為 ready、啟用 auto-merge、merge、派工 | 核准 pull request；略過 check 或核准 |

**為什麼每位開發者的 agent 各有自己的 GitHub App。** App 只擁有被授予的權限，與其擁有者的角色無關，所以它沒有 admin bypass。它的 token 一小時後過期。它不佔用 seat。而且由於每位開發者一個，commit 或留言會顯示是誰的 agent 做的。Personal access token 做不到這些：從 admin 帳號簽發的 token，即使是 fine-grained 的，仍然繼承 admin 可 bypass ruleset 的資格。`agentctl app-token` 在主機上產生 token，由 sandbox 的 proxy 注入，所以金鑰與 token 都不在 VM 內。

**Sandbox 永遠拿不到 App 的完整權限。** `tools/agentctl/profiles.py` 定義了兩種 token。`write` token 供交付程式碼或 spec 的 stage 使用，具有 contents: write、issues: write 與 pull requests: read。它可以 push branch，但不能開啟、重新指定目標或 review pull request。`read` token 供 review 與 triage 使用，具有 contents: read、pull requests: write 與 issues: write。它可以 review 與留言，但不能 push。沒有任何 agent token 同時擁有這兩種能力；只有 conductor 有。

**誰可以更新 `main`** 是第二個、獨立的限制。Ruleset `main-merge` 只允許 repository admin 與 Conductor App 更新預設 branch。讓 agent 無法 merge 的是這個 ruleset，而不是被縮減權限的 token：GitHub 的 merge endpoint 只需要 contents: write，而 `write` token 有這個權限。`main` 與 `main-checks` 這兩個 ruleset 沒有 bypass，所以 admin 與 Conductor App 也必須滿足每一個 check 與核准。

**為什麼 conductor 是獨立的 GitHub App。** GitHub 不允許作者核准自己的 pull request。如果雲端 agent 以你的身分開啟 spec pull request，你就無法核准它。所以 agent 只 push branch，由 Conductor App 開啟 pull request。此外，用預設的 `GITHUB_TOKEN` 開啟的 pull request 與進行的 merge 不會觸發其他 workflow，gate 就完全不會執行。本地的 conductor 基於同樣的理由以同一個 App 的身分行動：它用 Mac 上的金鑰自行產生該 App 的 token。如果它以你的身分行動，你就會成為它所開 pull request 的作者，而無法核准。

**雲端 session 是例外。** Claude Code on the web 與 Codex cloud 透過廠商自己的整合連到 GitHub，以你所連接的使用者帳號行動；你無法換成自己的 App。因此雲端 agent 以該帳號的身分行動。上述的 token 限制不適用於它，它不能做什麼取決於廠商的限制，以及沒有 bypass 的 ruleset。Layer 1 的 checklist 正是測試這一點：雲端 agent 是否能建立 release tag 或核准 pull request。若任一項成功，有兩條出路。為雲端服務連接一個獨立的機器帳號，代價是多一個 seat。或者停止使用雲端路徑，讓每個 stage 都在本地 sandbox 中執行（`via = "sbx"`），這不花錢，但需要 Mac 開機且 conductor 在執行。

## 6. Gate：merge 之前必須成立的條件

Ruleset 依 layer 分開，這樣 layer 2 才能單獨採用。`agentctl rulesets 2` 套用其中三個；`agentctl rulesets 3` 套用第四個。

Layer 2。第一個 `main` 沒有 bypass 清單，對人與 agent 一視同仁：

- 不可直接 push、不可 force push、不可刪除。只能透過 pull request merge，並採用 squash。
- 當 CODEOWNERS 所列的路徑被更動時，必須有 owner（人）核准。新的 push 會使先前的核准失效。

第二個 `main-merge` 限制誰可以更新 `main`：repository admin 與 Conductor App。它的 bypass 清單只讓這兩者免於這個 ruleset，不免於其他 ruleset。第三個 `tags` 只讓 admin 建立、移動或刪除任何 tag。`v*` tag 就是 release 的核准；其他名稱的 tag，在任何解析短 ref 名稱的地方都可能被當成 branch（git 會先在 tag 之中尋找 `origin/main`），所以 kit 自己的工具也使用完整的 ref 名稱（`refs/remotes/origin/main`）或 commit id。

Layer 3。第四個 `main-checks` 要求五個 check 全部通過，且 branch 與 main 同步，每個 check 都由 GitHub Actions app 回報（`integration_id: 15368`），所以來自其他來源、名稱相同的 status 不算數。它只能在 caller workflow 已進入預設 branch 並執行過之後才套用，因為它要求的 check 由那些 workflow 產生；若更早套用，會擋住每一個 pull request。

| GitHub 回報的 check | 它驗證什麼 | 由誰判定 |
|---|---|---|
| `ci / ci` | Lint、所有測試 | 程式 |
| `security / security` | 機密掃描、靜態分析 | 程式 |
| `ci / spec-verify` | 可追溯性：每個已核准的 test case 都對應到一個確實執行並通過的測試，且曾經通過的測試不得消失。Red-green：該 story 的測試在 main 上失敗（以 test runner 的回報為準），在 branch 上通過 | 程式 |
| `risk-gate / risk-gate` | 風險分級；T2 需要人對目前的 commit 核准 | 程式與人 |
| `agent-review`（commit status） | 另一個 agent 對實作的 review，以及對測試忠實度的 review | Agent |

名稱是「caller job / job」，因為專案的 caller workflow 呼叫的是 kit 的 reusable workflow。`layer-3-ci-zh-TW.md` 有說明。

**評判者不受 pull request 控制。** `spec-verify` 與 `risk-gate` 從 **base branch** 讀取專案設定，並以固定的 SHA 執行 kit，所以 pull request 無法更改評判它自己的規則。`ci` 則從 pull request 讀取，因為它本來就要執行該 pull request 的程式碼。`spec-verify` 本身不執行 pull request 的任何程式碼：測試在 `ci` job 中執行，結果以檔案形式交給 `spec-verify` 判定。這些檔案由執行過 pull request 程式碼的 job 產生，所以 `spec-verify` 把它們視為不受信任的輸入。Artifact 在 runner 暫存目錄中解開，位於兩個 checkout 之外，只有一般的 `*.xml` 檔案與 `collected.json` 會被傳遞下去，artifact 中任何地方出現 symbolic link 都會讓 job 失敗。這保護的是評判者，不是結果的內容，結果仍然是那個 job 寫了什麼就是什麼；見下方的限制。

**只有進入 `main` 的 pull request 會被評判。** `risk-gate` 也會在 review 上執行，而 review 事件無法依 base branch 過濾，所以當 pull request 的 base 不是預設 branch 時，它的第一個步驟會失敗，而不是略過。GitHub 把略過的 job 視為已通過的必要 check，而該結果在 pull request 被重新指定目標之後仍會留在 commit 上。一個在沒有新 push 的情況下被重新指定到 `main` 的 pull request，沒有 `ci`、`security` 或 `spec-verify` 的結果，所以在下次 push 之前都會被擋住。

**Draft。** Conductor 把 story 的 pull request 以 draft 開啟。在 draft 上，`ci` 只執行 lint，`security` 與 `spec-verify` 被略過。GitHub 把略過的 check 視為通過。這只有在兩個條件下可以接受：draft 不能被 merge，而且把它標記為 ready（`ready_for_review`）會在同一個 commit 上觸發完整的執行。當 implementation stage 完成時，conductor 把它標記為 ready，完整的 gate 才在那時執行。這樣可以節省 Actions 預算。

### 風險等級

由 `agentdev.toml` 中的 `[risk.*]` 設定：

- **T0** 僅文件（`[risk.t0] paths`）。Check 全綠就夠了。
- **T1** 屬於已核准 story 的程式碼變更。Check 通過加上 agent review 就夠了。
- **T2** 需要人核准。包括：guardrail 本身（`.github/**`、`agentdev.toml`、agent 設定、`AGENTS.md`、`CLAUDE.md`、掃描器設定等等）、spec、sprint 與產品文件（`human_gated`）、專案的高風險程式碼路徑（`high_risk`：預設為 auth、payments、migrations、infrastructure；專案必須依自己的目錄結構設定這份清單）、依賴 manifest 或 lock 檔案的變更（`dependency_manifests`，專案必須依自己的技術堆疊擴充這份清單）、超過大小門檻的 diff，以及不屬於任何 story 的程式碼變更。

測試檔案不是 T0。削弱一個測試就是行為上的改變。

變更的路徑讀自 `git diff -z`。沒有 `-z` 時，git 會把含有特殊字元的路徑加上引號，而加了引號的路徑不會符合任何 pattern。

`risk-gate` 會把等級發布兩次。Pull request 上的 label `tier:T0`、`tier:T1` 或 `tier:T2` 是給人看的。Head commit 上的 commit status `risk-tier/T0`、`risk-tier/T1` 或 `risk-tier/T2` 是 conductor 決定能否啟用 auto-merge 時讀取的。Agent 的 token 具有 issues: write，可以編輯 label，但不能寫入 commit status。當一個 commit 帶有多個這類 status 時，以最嚴格的為準；沒有任何 status 的 commit 視為 T2。

### 「AI 說它會寫測試 XYZ，不代表它真的寫了」

在你已核准的 story 中，每個 test case 都有一個 ID（`TC-012-03`，位數由 `[stories] id_digits` 設定）。接下來有四層檢查，前三層不依賴 agent 所說的任何事：

1. **可追溯性（Traceability）。** 測試名稱必須帶有 TC ID。CI 讀取 test runner 輸出的 JUnit XML，確認每個 ID 至少有一個確實執行並通過的測試。被略過的、不存在的，或只在註解中提到的測試都不算。依據是執行結果，而不是對原始碼的搜尋。專案的 `[tests] test_cmd` 必須執行所有測試，並把 JUnit XML 寫到 `junit_glob` 找得到的地方；kit 為 Python 專案提供了 unittest 包裝器（`agentctl junit-unittest`）。在該包裝器中，標記為 `expectedFailure` 且斷言失敗的測試會被回報為略過，所以它永遠不會算作通過的 test case。
2. **Red-green。** Pull request 的測試檔案，以及任何提到該 story 的 TC id 的檔案，會疊加到乾淨的 main checkout 上並在那裡執行，它們必須失敗。在 pull request 上它們必須通過。像 `assert True` 這樣的空測試在 main 上就已通過，因此會被擋下。在 main 上的執行會先執行 `setup_cmd`，這樣測試就不會僅因缺少依賴而在那裡失敗。「Red」必須是 test runner 回報出來的結果。在 main 上被略過的測試不被接受為 red。如果在 main 上的執行完全沒有產生報告，或 `setup_cmd` 本身在那裡失敗，這個 check 就會失敗，因為什麼也沒有被證明。報告確實存在、但其中缺少某個測試時，只有在該報告中有一個失敗或錯誤屬於該 story 所疊加的某個測試檔案（以不含副檔名的檔名比對）時，才接受它為 red。常見的原因是該檔案在 implementation 存在之前無法被 import。main 上其他不相關的失敗不算數。
3. **不得消失。** 在 main 上曾經通過的 TC 必須仍然通過，即使它的 spec 在同一個變更中被刪除。要移除一個 TC，唯一的方法是把它列在 specs 目錄中的 `retired.toml`（`retired = ["TC-012-03"]`）。該檔案與 spec 都受 CODEOWNERS 保護，所以 agent 無法悄悄刪除一個 TC。比較時使用 main 上最新、已完成且有結果的 `ci` 執行，最多五次，不論那些執行的結論為何，只要某個 TC 在其中任何一次通過過，它就必須仍然通過。Artifact 不存在或已過期的執行會被略過。列出或下載失敗會讓 job 失敗；它不會被誤認為「沒有歷史」。如果沒有任何執行有結果（新專案，或 artifact 在 90 天後已過期），`spec-verify` 只會發出警告。
4. **忠實度稽核（Fidelity audit）。** Review agent（與撰寫測試和實作的 session 不同）逐一判斷每個 TC：測試的斷言是否真的驗證了所描述的行為？這一層涵蓋前三層看不到的情況：測試存在，也經歷 red 與 green，但驗證的是錯的東西。

前三層由單一的 check `spec-verify` 執行。Merge 之後，`evidence` workflow 會把「AC → TC → 測試 → 結果」的表格貼到該 story 的 issue 上。你讀的是那張表，不是程式碼。

這個保證有三項限制。第一，它確保你核准的每個 TC 都有一個會隨行為改變的、確實執行的測試，但不保證 TC 清單本身是完整的。那取決於 PO 的提問，以及你核准 story 時的閱讀。第二，測試結果由 pull request 的程式碼產生，agent 能直接寫出一份偽造的結果檔。對此沒有硬性的防禦。它依賴 `test_cmd` 與它所執行的檔案受到保護、review agent，以及每週的抽查。第三，red-green 顯示 story 的測試在 main 上不通過，但沒有顯示原因。一個刻意寫成在 main 與 branch 上行為不同的測試（例如檢查某個檔案是否存在），仍然可以滿足它。要抓出這一點，是忠實度稽核的工作。

### `agent-review` 的強度

這是五個 check 中唯一由 agent 判定的，也是最弱的。這一點應當誠實說明。

Claude 的 review 以 workflow `agent-review` 執行，由 conductor 從預設 branch 啟動。Reviewer 在預設 branch 的 checkout 中執行，pull request 則作為資料 checkout 在旁邊，所以 Claude Code 的設定與 hook 絕不會來自 pull request。Workflow 首先檢查 pull request 是否為 open、是否來自這個 repository、是否以預設 branch 為目標。一次 review 針對一個 commit：conductor 傳入它記錄在 dispatch marker 中的 commit。如果 job 開始時 head 是不同的 commit，job 會在 review 之前失敗，conductor 會針對新的 head 重新要求。進行 review 的 job 持有唯讀 token 與受限的工具清單，並把它的結論寫在兩個 checkout 之外。另一個獨立的 `publish` job 從不接觸 pull request 的檔案，由它貼出 finding 並設定 status。只有在 review 步驟本身成功時結論才算數；否則 status 是 failure，絕不是 pass。實作 agent 的 token 無法寫入 commit status，所以它無法偽造。

對於不是 Claude 的 reviewer（例如 Codex），由一個 bridge job 把列在 repository 變數 `REVIEW_BOTS` 中的 bot 所貼出的 review 轉成 status。如果 review 是改在一般的雲端 session 中進行，reviewer 與 implementer 可能以同一個 GitHub 身分行動，兩者無法以身分區分。對於由留言啟動或在本地 sandbox 中執行的 review，prompt 會指名要 review 的 commit，並告訴 reviewer 在 head 是不同 commit 時停止。那是對 agent 的指示，不是像 workflow 的檢查那樣的強制執行。

剩下的，就是這個 check 最弱的原因。Reviewer 讀的是不受信任的文字：diff、commit message 與 pull request 的檔案。那些文字可以說服它做出錯誤的結論。隔離限制的是被誤導的 reviewer 能做什麼，不限制它得出什麼結論。

所以這個設計不讓任何硬性的保證依賴 `agent-review`。高風險的變更有人核准，測試的存在與有效性有機械式的 check。Agent review 提供語意層面的檢查，而錯誤放行的代價受其他 gate 所限制。

## 7. 從一句話到 production

```
Stage 0  You say one sentence (PO chat, or write it into the roadmap)
Stage 1  PO agent produces the story            → you approve the spec pull request 【Gate 1】
Stage 2  design   the design agent writes the design document
Stage 3  tests    the test agent writes tests from the story alone (they must be red at this point)
Stage 4  impl     the implementation agent turns the tests green
Stage 5  review   the review agent reviews the implementation and audits the tests
Stage 6  all five checks green → merge → evidence table posted to the issue
Stage 7  you push a v* tag → deploy to production                         【Gate 2】
```

每個 stage 都是全新的 agent session，不記得前一個 stage。它需要的一切都在 spec、story issue、branch 與 commit 歷史中，它的指示就是 kit 為該 stage 準備的 prompt。

### AI Product Owner

你的需求通常只有一句話。PO（`prompts/product-owner.md`）會把它變成你能在兩分鐘內核准的 story。

- 它先讀 `[paths] product` 之下的領域文件與相關的既有 story，並檢查新需求是否與既有行為衝突。
- 它最多問五個問題，而且只問那些「會改變要建構的東西、事後又難以復原」的：付款流程與訂單狀態、失敗或被拒絕之後會怎樣、誰有權限、資料保留，以及對外通知。其餘的它自己決定，並把那些決定列為假設。
- 它產出 `story.md`（英文，agent 據以實作與 review）、`story-<lang>.md`（你據以核准的語言，預設為 `zh-TW`，當 `[stories] translation` 為空時省略）以及 `spec.toml`（機器可讀）。每個 story 檔案以 `max_lines` 為上限（預設 80）。範例見 `examples/specs/000-example/`。

你核准的是翻譯版，agent 讀的是英文版。兩者在語意上的落差是雙語 story 的主要風險。這以三層來處理。`spec-lint` 檢查兩個檔案的 AC 與 TC ID 相同且順序相同，章節也相同。CI 檢查這兩個檔案在同一個 pull request 中一起變更。PO 在撰寫之後逐項比對，review agent 再比對一次，並把語意上的差異視為阻擋項。前兩層是機械式的。第三層是 agent 的判斷，不是硬性的保證。如果兩者不一致，以英文版為準，因為那是實際被實作的版本。

兩種模式。**chat**：你在手機或桌面上與它對話，適合想深入討論的需求。**async**：你只在 roadmap 中加一行，conductor 派出 PO 起草一個 spec pull request，問題寫在說明中，你以 review 留言回答。尚未核准的 spec pull request 以 `max_open_spec_prs`（預設三個）為上限，以免堆積。

你在 GitHub 上核准該 pull request 就是核准。手機 app 就夠了。不使用 label 作為核准的訊號，因為 agent 可以更改 label。Conductor 會把 spec 與 sprint 的 pull request 以 ready for review 的狀態開啟。你核准之後，conductor 會對它啟用 auto-merge，在 check 全綠時自動 merge。這是你的決定，不是 conductor 的判斷，所以它不取決於 `auto_merge_tiers`。

### 角色分配

`agentdev.toml` 中的 `[roles.developers.<login>.stages]` 針對每位開發者設定每個 stage 使用哪個 harness，並帶有備援順序；`default` 涵蓋沒有 assignee 的 story 與沒有列出的人。某個 story 屬於誰，來自已核准的 sprint 檔案：`assignee` 是預設值，另有一個選用的 `[owners]` table 可為個別 story 指定另一位開發者。不使用 issue 的 assignee。`[roles.harness.<name>]` 說明每個 harness 如何啟動：`via = "http"`（雲端排程任務的 API trigger）、`"comment"`（啟動雲端任務的提及，例如 Codex cloud）或 `"sbx"`（全新的本地 sandbox，僅在 conductor 於該台 Mac 上執行時可用）。這裡沒有假設任何特定廠商：只用 Codex 的專案就只列出 Codex。

原則是讓 reviewer 與 implementer 是不同的 session，且在有多家廠商時來自不同的廠商。實務上的限制是額度。Implementation 是最耗 token 的 stage，review 最輕，所以把 implementation 放在某人較大的訂閱上，把 review 放在較小的那一個上。

| 設置 | 誰來 review | 你放棄什麼 |
|---|---|---|
| 一個人，一家廠商 | 同一個 harness 的全新 session | 跨廠商的 review。主要的保證由機械式的 check 承擔 |
| 一個人，多家廠商 | 與 implementer 不同的廠商 | 只要兩邊的額度都還有，就什麼都不放棄 |
| 多個人，各自有自己的 AI | 每個人自己那一組允許的任何選擇 | 只有一家廠商的人，其 story 得到同廠商的 review |

在每一種設置中，T2 變更仍然交給人。只有一個人時，那個人同時也是 director。

如果每個 session 都握有同樣的權力，把角色分給不同的 session 並不夠。所以每個 stage 的 sandbox 只拿到該 stage 需要的東西：

| Stage | 它的 GitHub token 可以 | 網路 | 可編輯 |
|---|---|---|---|
| design、tests、impl（以及它的 fix 與 conflict 執行） | Push branch；留言、加 label。不能開啟、重新指定目標或 review pull request | 原始碼控管、模型供應商、套件 registry | 程式碼與測試；不含 guardrail，不含已核准的 spec |
| review、triage | 讀取 repository；留言、加 label、review。**不能 push** | 僅限原始碼控管與模型供應商 | 沒有任何它可以交付的東西 |
| product-owner、planner | Push branch；留言、加 label。不能開啟、重新指定目標或 review pull request | 僅限原始碼控管與模型供應商 | Spec、sprint、產品文件；不含 guardrail |

前兩欄是硬性控制。GitHub 以 App 權限的子集產生 token，而 sandbox 的網路政策是依每個 sandbox 設定的，所以不論 prompt 怎麼寫，試圖 push 的 review agent 都會被 GitHub 拒絕。Sandbox 絕不重複使用，所以 review 的 sandbox 無法繼承 implementation sandbox 曾被允許的套件 registry。第三欄是 harness 的 deny 規則，屬於軟性的一層。這張表以常數的形式存在已安裝 kit 的 `tools/agentctl/profiles.py` 中，所以 branch 無法給自己更多權限。

兩項限制。GitHub 權限是依 repository 而不是依路徑：「撰寫測試的人不得碰 implementation」與「implementer 不得削弱測試」無法用 token 表達，仍由 `spec-verify`、CODEOWNERS 與 review 負責。而且這種區隔只存在於 sandbox 路徑：不論哪個 stage，雲端 session 都以你連接的帳號行動。

## 8. 持續運作：conductor

當你不在時，由 conductor 讓工作往前推進。

### 它是什麼，以及為什麼是確定性的

它是一支沒有狀態、沒有 LLM 的程式（`agentctl conductor`，執行 `tools/agentctl/reconcile.py` 中的 reconcile 邏輯）。每一次 pass，它都讀取完整的當前狀況：sprint、spec、issue、pull request、check 結果。它算出現在接下來應該發生的事，然後去做。它自己什麼都不記得。所有記憶都在 GitHub 上（label、issue 連結、隱藏的 marker 留言）。所以中斷、重跑與漏掉的事件都無妨：下一次 pass 會得到同樣的結論。

它不是長時間執行的 LLM session，理由如下。長 session 的狀態在它的 context 中。Context 會被壓縮、指示會遺失，中斷之後 session 無法完整還原，它的行為難以稽核，而且它持續消耗額度。狀態在 GitHub 上、每次判斷都用全新的 context，這些問題就不存在。同樣的輸入永遠得到同樣的結果、不使用額度，而且可以完整地做單元測試。

既有工具的經驗也指向同一個方向。Gas Town 以 LLM 作為協調者，其作者說它在一次模型升級之後就不能用了，agent 一再轉而修改 harness 本身（二手報導）。Claude Code agent teams 的文件記載 lead 會提早結束，任務狀態落後並阻擋下游的工作。Anthropic 關於長時間執行 agent 的工程文章主張每個 session 都從全新的 context 開始，並把連續性保存在檔案與 git 中。最接近這個設計的是 OpenAI Symphony：以 issue tracker 作為事實來源的確定性 reconcile 迴圈。它只支援 Codex 與 Linear，所以這個 kit 採用它的做法，而不是它的實作。

它讀回的內容不會被盲目信任。Marker 留言只有在由 conductor 自己的 login，或由 `[roles]` 中列出的人所寫時才被採信。Agent 可以在 issue 上留言，所以來自其他人的 marker 會被忽略。Story 的 pull request 是從這個 repository 到預設 branch 的、open 的那一個，沒有的話才是已 merge 的那一個。已關閉的 pull request、進入其他 base 的 pull request，以及來自其他 repository 的 pull request 絕不會被選中。只有 spec 所定義的 branch 名稱 `story/NNN-slug` 才是該 story 的 branch。

### 它在哪裡執行

Conductor **只在一台 Mac 上**執行，在終端機中：`agentctl conductor`。它每 180 秒輪詢一次（`--interval`）。每次 pass，它從 `origin/main` 的全新 worktree 讀取 spec、sprint 與 `agentdev.toml`，而不是你的工作目錄，並以 Conductor App 的身分在 GitHub 上行動，不是以你的身分。`agentctl conductor --dry-run` 執行一次 pass、印出計畫，而不採取任何行動。Ctrl-C 停止它。

沒有 GitHub Actions 的 conductor、沒有 lease，也沒有交接。Lock 檔案阻止同一台 Mac 上為同一個專案啟動第二個 conductor。另一台 Mac 上的第二個 conductor 不受支援，也沒有任何機制偵測它（已知限制）。當 Mac 睡眠或終端機被關閉時，沒有任何事會推進。已派到雲端的 agent 會繼續工作，但它們的 push 要等下一次 pass 才能得到 pull request、review 或 merge。連續三次 pass 失敗之後，它在每次 pass 之間等待 15 分鐘。

Conductor 的憑證放在 repository 之外，位於 `~/.config/agent-dev/<owner>-<repo>/conductor.env`：Conductor App 的 id 與它私鑰的路徑（`CONDUCTOR_APP_ID`、`CONDUCTOR_APP_KEY`）、`DEVELOPER`（你的 GitHub login），以及你使用的 dispatch secret。你 Mac 上的 conductor 只持有你的憑證。它派出指派給你的 story 與沒有指派的 story，並延後指派給其他開發者的 story；本地 sandbox（`via = "sbx"`）只會在該 story 所屬開發者的 Mac 上啟動。

GitHub Actions 這一側有三項工作：layer 3 的 reusable workflow、每日的 director's brief（它也執行 `agentctl budget`），以及 review workflow 所需、位於 `conductor` environment 的 secret。該 environment 的 deployment branch 規則只允許預設 branch，所以來自任何其他 ref 的執行都拿不到 secret。Secret 必須建立為 `conductor` 的 environment secret，而不是 repository secret。指名的開發者所做的 review 只使用該開發者的 `_<LOGIN>` secret，缺少時會在任何東西被寫入之前就讓 dispatch 失敗。

Pull request 由 conductor 開啟。Story branch 得到 draft。Spec、sprint 或 chore branch 得到 ready for review 的 pull request。作者是 Conductor App，所以人可以核准。

### 順序的判斷從哪裡來

程式無法判斷哪個 story 應該先做。它也不需要，因為判斷發生在別處：

**在規劃時，由 agent 判斷、由你核准。** Planner（`prompts/planner.md`）讀取所有候選 story 與程式碼，並為每個 story 決定 `depends_on`（必須先 merge 的 story）、`touches`（它將更改的模組與共用資源）與 `priority`。這些寫在 `spec.toml` 中，隨 sprint pull request 交給你核准。你核准的是範圍與優先順序。

**在執行時，由程式計算。** 當以下條件成立時，story 可以開始：它所依賴的 story 都已 merge、它沒有被標記為 blocked、它的 `touches` 與進行中 story 的 `touches` 沒有交集，而且沒有超過 `wip_limit`。符合條件的依優先順序、它能解鎖的下游 story 數量，以及編號排序。一個已經開始、卻因為 triage 後來加入的依賴而必須等待的 story 會被 park：它不佔用名額，也不佔用 `touches` 的宣告。當多個已開始的 story 同時再次符合條件時，編號最小的先得到新工作，在 `wip_limit` 之內，且絕不會有兩個碰同一個東西的同時進行。

**當出問題時，由短命的 triage session 判斷。** 規劃好的依賴一定會有錯誤。常見的一種是做到一半才發現還需要另一個未完成的 story。當 conductor 偵測到某個 stage 反覆失敗或停滯時，它會啟動 triage agent（`prompts/triage.md`）。它只能做三件事：加上一個「blocked by」連結、要求重試並說明該如何改變做法，或附上選項向你 escalate。它不能更改 spec、不能更改 sprint 的範圍，也不能碰程式碼或測試。

### 它做什麼，不做什麼

- 當 agent 已 push 一個還沒有 pull request 的 branch 時，它會開啟一個。
- 當某個 story 在等你時，它繞過去，做別的事。等你的 story 不佔用名額。紅色的 `risk-gate`（等待核准的 T2 變更）就是這樣的等待。它絕不會被回報為「ready to merge」。
- 當 sprint 中每個未完成的 story 都卡在你身上時，它停下一切，並通知你一次。
- 當 sprint 完成而下一個尚未核准時，開發停止。只有 spec 的起草繼續。它不會自行擴大範圍。當已 merge 的 story 比例達到 `draft_next_sprint_at` 時，它會要求起草下一個 sprint。
- 當 pull request 落後於 main 時，它會更新 branch。有衝突時，它會派出解決衝突的任務。
- Fix、衝突解決與 review 都綁定於它們被派出時所針對的 commit。在 branch 移動之前，fix 都算作進行中。每個新的 commit 都需要自己的 review 結論。
- 從 conductor 執行的位置無法送出的 stage（為另一位開發者的 story 啟動本地 sandbox）會被延後，且不寫入任何東西。
- 在先前的 sprint 中已 merge 的依賴視為已滿足。它以 spec 所定義的確切 branch 名稱辨識。
- 當 main 變紅時，它停止派工，只派出一個修復任務。
- 當某個 harness 的額度用盡時，它切換到 `[roles]` 中的備援。全部用盡時，它就等待。
- 當所有 gate 都通過時，它啟用 auto-merge，但只針對列在 `auto_merge_tiers` 中的等級。等級來自 `risk-tier/*` commit status，不是 label；只有描述為針對這個 pull request 與預設 branch 的「pull request #N into BRANCH」的 status 才算數。Auto-merge 只會針對做出該決定時所依據的 commit 啟用（`gh pr merge --match-head-commit`）：如果 branch 已經移動，GitHub 會拒絕，下一次 pass 再重新決定。GitHub 會在之後的 push 之間保留 pull request 上的 auto-merge 請求，所以每次 pass，conductor 都會檢查每個已開啟 auto-merge 的 story pull request，當該 pull request 不再符合當初啟用時的條件時就撤回：不是 draft、沒有尚待處理的人工 review、四個機械式 check 與 `agent-review` 皆為綠色，且它的等級在 `auto_merge_tiers` 中。當 main 為紅色、當計畫已損壞、或當該 story 不在 sprint 中時，它也會撤回，即使該次 pass 提早返回也一樣。當 pull request 重新符合條件時，它會再次啟用。在 push 與下一次 pass 之間，該請求仍然是有效的；這個空窗可能放行什麼，見限制一節。

### Fuse

- **Kill switch**：把 repository 變數 `CONDUCTOR_PAUSED` 設為 `true`。它在每次 pass 都透過 API 即時讀取，所以已在執行的 conductor 會在一次 pass 之內停止。暫停期間，conductor 不派工，也不開啟 pull request。它只做一件事：把每個已開啟 auto-merge 的 open pull request 的 auto-merge 關掉，因為否則 GitHub 會在其 check 轉為綠色時自行 merge 這樣的 pull request。這發生在下一次 pass，而不是你設定該變數的那一刻，而且在 Mac 關機時完全不會發生。若要立即停止，也請自己執行 `gh pr merge NUMBER --disable-auto`。讀不到的變數不會被當成未設定（格式錯誤的 `CONDUCTOR_QUOTA` 項目會逐項被忽略）：`CONDUCTOR_PAUSED`、`CONDUCTOR_BOT` 與 `CONDUCTOR_QUOTA` 會優先且一起被讀取，其中任何一個讀不到時，該次 pass 的行為就如同已暫停，並仍然撤回 auto-merge。一旦某次 pass 看到暫停，或讀取變數失敗，派工就會立即停止。已開啟的 auto-merge，要等到某次 pass 能成功列出 pull request 並呼叫 GitHub 之後，才算已被撤回。
- **上限**，全都在 `[conductor]` 之下：同時進行的 story 數（`wip_limit`）、每天開啟的 pull request 數（`max_prs_per_day`）、同一個 stage 的派工次數（`max_attempts`）、fix 與 review 的輪數（`max_fix_rounds`）、每個 story 的 triage session 數（`max_triage`）、stage 可以花費的時間（`stage_timeout_minutes`）。超出上限時，它會以 `needs-human` 項目向你 escalate。它不會無止境地重試。
- **被 park 與等待中的 story。** 被 park 超過 `max_parked_hours`（72）的 story 會被 escalate，在 `max_dispatches_per_story`（15）次 session 之後即將再啟動 session 的 story 也是；兩者都從上一次 escalation 起算，所以有人處理過某個 story，就等於給它一份新的額度。Escalation 會指出正在等待它的 story。等待某個人的 story 會在 `remind_after_hours`（48）之後再次被提及，每次等待一次。Session 正在執行的 story 一律被放行，所以它的逾時與重試會被檢視，而回來的 story 絕不會與它同時執行。細節：[layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)。
- **Dispatch 在送出之前就先被記錄**，若送出失敗，該記錄會被撤回。所以 dispatch 可能重複，但絕不會遺失。

### Actions 預算

GitHub 以金額衡量額度：Team 方案包含每月一筆金額（`monthly_allowance_usd`，是估計值；請查看 GitHub 的帳單頁面）。**每個 job 的時間都向上進位到整分鐘**，所以只執行 5 秒的 job 也算一分鐘。這條規則塑造了設計：

- 測試套件只在必要的次數內執行：在 head 上一次，加上對 story branch，在 base 上疊加測試檔案再一次。兩者在同一個 job 中進行。
- Draft pull request 只執行 lint。完整的 gate 留到 implementation 完成之後。
- Agent 在每個 stage 結束時只 push 一次。
- 不執行 pull request 程式碼的輕量 job 可以使用較便宜的 runner，以 repository 變數 `LIGHT_RUNNER` 設定。

`agentctl budget` 從 Actions 的 job 記錄估算當月用量，並回報在每日的 brief 中。這些是估計值，尚未與帳單比對過。**溢出到 self-hosted runner 是關閉的**（`overflow_runner = []`）：`ci` 與 `security` 會執行 pull request 的程式碼，所以這樣的 runner 必須是專用的、不持有任何憑證，且每個 job 都重新建立，而 kit 並未提供。當額度用盡時，CI 停止，在下個月開始或你付費購買更多額度之前，沒有任何東西能 merge。負責判定的 job 一律留在 GitHub 代管的 runner 上：被 pull request 程式碼碰過的機器，不能用來判定那份同樣的程式碼。

### Agent 在哪裡執行

| 位置 | 如何啟動 | Mac 是否需要開機 |
|---|---|---|
| Claude Code 雲端 session | Conductor 呼叫排程任務的 API trigger（`via = "http"`） | Conductor 需要，用來派工與處理結果 |
| Codex cloud | Conductor 在 pull request 或 issue 上留下 `@codex` 留言（`via = "comment"`） | 同上 |
| Claude review | `agent-review` workflow，由 conductor 啟動 | 同上 |
| 本地 Docker Sandbox，clone 模式 | Conductor 直接啟動（`via = "sbx"`） | 需要，且 conductor 要在那裡執行 |

哪條雲端路徑實際可行，必須在你的帳號上確認。對於不可行的路徑，請在 `[roles.harness.*]` 中改為 `via = "sbx"`。

## 9. 分階段開啟 auto-merge

新專案的測試還不夠好，不足以作為 merge 的依據，所以 `auto_merge_tiers` 預設為空（**shadow mode**）：每個 gate 照常計算並回報，但按下 merge 的是你，conductor 只會通知你「這一個可以 merge」。既有專案採用 conductor 時也是這樣。

觀察一陣子。當你確認這些 gate 的結論與你自己的判斷一致之後，設定 `auto_merge_tiers = ["T0"]`，再設為 `["T0", "T1"]`。每一次都是更改 `agentdev.toml` 的 pull request，所以由人核准。T2 一律需要人核准，永遠不能列入。

Auto-merge 的可信度受限於測試的品質。這就是要分階段進行的原因。每一步之前要觀察什麼，見 [layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)。

## 10. 你的日常

你做四件事：

1. 在 roadmap 中加一行，或對 PO 說一句話。
2. 核准或回答 spec pull request。
3. 核准 sprint pull request。
4. Push release tag。

你看兩個地方：

- **Director's brief**：一個固定的 issue，每天更新。內容包括 sprint 進度、等待你決定的事項、卡住的項目、新 merge 的項目，以及本月 Actions 用量的估計。每週一還會多一個稽核區段：每個等級的 merge 數、revert 數、escalation 數，以及隨機抽出的幾個沒有人參與就 merge 的 pull request，供你抽查。這些數字來自 GitHub，不是 agent 對自己的說法。
- **GitHub 通知**：需要你 review 的 pull request 與提到你的 issue，就是你的決策佇列。Escalation 會提及人；它不會指派 issue。

## 11. 已驗證與尚未驗證

**尚未有任何部分在真實的 GitHub、Docker Sandboxes、廠商的雲端服務或 Mac 上執行過。** 這一節是整個 kit 唯一的清單；每個 layer 的文件會說明它的 checklist 能確認其中哪些項目。

**開發期間已驗證：**

- 這些工具的邏輯有 174 個單元測試，全部通過：風險分級、設定、init、雙語 spec 與文件檢查、可追溯性、red-green 判定、conductor 的排程邏輯（reconcile）、預算估算、身分與 token 設定檔、指令封鎖 hook，以及安裝程式。
- Red-green 已在真實的 git repository 上端到端執行過，分為 collect 與 judge 兩部分：空測試被擋下，改成真正的測試之後就通過。當 collect 步驟沒有執行時，判定是 fail 而不是 pass。
- `spec-verify` 中只保留一般結果檔案的步驟，已依 workflow 中所寫的樣子，對一個含有 symbolic link 與多餘檔案的 artifact 執行過。
- `ci` 的 baseline 步驟已對一個假的 `gh` 執行過：七次執行，包含缺少與已過期的 artifact、被拒絕的列出，以及被拒絕的下載。
- 測試流程已在一個暫時的 repository 中以隨附的 runner 執行過：誠實的 story 通過兩位評判者，而空洞的測試、沒有 id 的測試與 expected failure 都被拒絕。
- Conductor 的 GitHub 介面層已對模擬的 `gh` 執行過：派工、在工作送出之前留下 marker、送出失敗時撤回它、把 draft 標記為 ready、單一動作失敗不影響其他動作，以及忽略偽造的 marker 與誘餌 pull request。
- 工作目錄中的惡意模組（`agentctl.py`、`json.py`、`tomllib.py`），在工具透過 launcher 或 `python3 -I tools/run.py` 啟動時，無法取代工具。
- `sandbox/sbx.sh` 已對假的 `sbx` 執行過，驗證它的拒絕情形（目錄樹中看起來像機密的檔案、已存在的 sandbox 名稱、錯誤的 story id、stage 或 harness）、網路探測的結果、名稱長度的上限，以及兩個 repository 名稱的衝突。它們背後的 `sbx` 指令則未執行過。
- Workflow 通過 actionlint，shell 腳本通過 shellcheck。

**尚未驗證：**

*Layer 1，isolation（由 [layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md) 的 checklist 確認）。*

- 真實 Mac 上的 Docker Sandboxes：腳本所使用的 `sbx` 指令、clone 模式、clone 模式掛載的是整個專案目錄（包括被忽略的檔案）、proxy 是否把 App token 注入到透過 HTTPS 的 `git push` 中、sandbox 內的 home 目錄路徑，以及每個 harness 的 headless 執行。
- 設定所依賴的三個 `sbx` 指令：`sbx settings set skills.defaultMode off`、`sbx policy init deny-all` 與 `sbx policy reset --force`；以及只對單一 sandbox 生效的網路規則（`sbx policy allow network --sandbox NAME HOST`）。
- 真實 sandbox 內的網路探測：那裡是否有 `curl`、被 sbx proxy 拒絕的請求從內部看起來如何，以及 `github.com` 是否連得到。以及 sbx 是否接受腳本所產生的最長 sandbox 名稱。
- 對真實 API 產生 agent App token（`agentctl app-token`），並把它縮減為較少的權限：具有 pull requests: read 的 push token，在嘗試開啟或 review pull request 時被拒絕。
- 連接到個人 admin 帳號的雲端 session 在 GitHub 上能做什麼。
- `.claude/settings.json` 中的 sandbox 與權限語法是否符合目前的 Claude Code 版本，以及 `agentctl harness-settings` 產生的 harness deny 規則是否生效。

*Layer 2，GitHub protection（由 [layer-2-github-zh-TW.md](layer-2-github-zh-TW.md) 確認）。*

- 如第 6 節所述，`main-merge` ruleset 疊加在 `main` ruleset 之上；`agentctl rulesets 2` 與 `3` 在真實 repository 上建立四個 ruleset；以及 `integration_id: 15368` 指的是 GitHub Actions，並接受由 workflow job 寫入的 `agent-review` status。
- 來自 reusable workflow 的必要 check，是否如 ruleset 所預期，以「caller job / job」的形式回報（`ci / ci` 與其他）。
- 在 Team 方案的私有 repository 上，帶有 deployment branch 規則的 environment：來自預設 branch 以外任何 ref 的執行，是否拿不到 `conductor` environment 的 secret，以及被呼叫的 reusable workflow 是否能使用它們。
- Team 方案在私有 repository 上的功能邊界：ruleset 與 auto-merge 可用；merge queue 與 environment 的 required reviewer 不可用。後者就是 release 使用 tag protection 的原因。

*Layer 3，CI gates（由 [layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md) 確認）。*

- 真實 GitHub 上的 reusable workflow：從 codeload 以 SHA 抓取 kit、`secrets: inherit` 傳入被呼叫的 job、reviewer 從 runner 暫存目錄讀取它的 prompt，以及 `agentctl pins` 對真實 caller 的檢查。
- `anthropics/claude-code-action` 目前的輸入參數（`github_token`、`--allowedTools` 引數、`--tools` 是否限制 reviewer 的工具）；review bot 的帳號名稱，以及它供 `REVIEW_BOTS` bridge 使用的 review 格式。
- `actions/download-artifact` 對惡意封存檔的行為。
- Commit status `risk-tier/*` 是否出現在 conductor 讀取等級的 `statusCheckRollup` 中。
- 在 draft pull request 上被略過的必要 check，在它被標記為 ready 之後的行為：在它變成可 merge 之前，同一個 commit 是否會出現新的完整執行。
- 預算估算與 GitHub 帳單之間的實際差距，以及較便宜 runner 的實際 label。

*Layer 4，conductor（由 [layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md) 確認）。*

- Conductor 對真實 GitHub API 的運作，特別是 issue 依賴連結與 check status 的讀取，以及以 Conductor App 的 token 讀取 repository 變數（讀取被拒絕會讓每次 pass 的行為都如同已暫停）。
- 以 Mac 上的金鑰產生 Conductor App 的 token。
- 以 API 觸發 Claude 雲端排程任務的介面，以及以 `@codex` 留言啟動任務是否可行、對留言者的身分有什麼要求。
- GitHub 對已核准的 spec 或 sprint pull request 所回報的 review decision、Conductor App 對它啟用 auto-merge，以及隨後的 merge。`gh pr merge --match-head-commit` 與 `--disable-auto` 以 Conductor App 的身分執行。以及 GitHub 在 push 之間保留 auto-merge 請求，與 conductor 撤回它。
- 從一句話到一個已 merge 的 story 的完整迴圈，這正是 layer 4 的 spike 要證明的。

## 12. 已知限制

**信任與範圍**

- 專案上的人是受信任的。這個設計防禦的是失控的 agent 與 prompt injection，不是內部人員。
- 你貼進 PO chat 或 issue 的內容會進入廠商的 context，不在隔離範圍內。
- Docker Sandboxes 的版本是 0.x。它的指令可能改變。
- 持續運作的能力受訂閱額度所限。額度用盡時，工作會變慢，但不會失敗。
- 雲端觸發依賴兩家廠商仍在演進的功能。備援是本地 sandbox，但它需要 Mac 開機且 conductor 在執行。
- 當你不在時，等待你決定的事項會累積。這是 director 模式中唯一由你決定節奏的部分。

**Layer 1，isolation**

- 在 clone 模式中，agent 的工作在它 push 之前只存在於 VM 內。沒有 push 就結束的 stage，除了它的 log 之外什麼都不會留下。
- Clone 模式讓 agent 看見整個專案目錄，包括被忽略的檔案。機密的檢查只看檔名。名稱不同的機密不會被發現，每個 sandbox 都讀得到它。
- VM 內的訂閱登入狀態，理論上可能被惡意的 repository 內容竊取。對外連線的 allowlist 降低這個風險，但沒有消除它。
- 網路探測是在 sandbox 建立時，對三個主機做的抽查。它不能證明實際生效的 allowlist 等於專案的清單，也無法區分來源伺服器自己回的 403 或 5xx 與政策拒絕。
- 每個 stage 各自的權限只存在於 sandbox 路徑。在雲端 session 中，每個 stage 都以你連接的帳號行動。
- 雲端 session 以你連接的個人帳號行動。在 layer 1 的 checklist 執行完畢之前，請假設雲端 agent 能在 GitHub 上做該帳號能做的任何事，只受沒有 bypass 的 ruleset 所限制。Release tag 的 ruleset 讓 admin 可以 bypass，所以它是要測試的項目之一。該帳號同時也是列出的 human，所以 conductor 會相信從雲端 session 寫出的 marker 留言。
- Conductor App 的私鑰在執行 conductor 的 Mac 上。它放在 repository 之外，任何 sandbox 都看不到，但它在主機上。

**Layer 2，GitHub protection**

- Review token 可以寫入 pull request。它不能 push 或 merge，但 token 本身沒有任何東西阻止它開啟或編輯 pull request。
- Conductor 的 login 不論有沒有 `[bot]` 後綴，都被接受為 marker 的作者。所以 login 等於 Conductor App 的 slug 的人，會被當成 marker 作者而被採信。那個人還必須是 collaborator 才能留言。
- 指名開發者的 secret 用於該開發者的 story，但沒有任何機制檢查存放在 `NAME_<LOGIN>` 之下的值真的是那個人的憑證。

**Layer 3，CI gates**

- 修改 caller workflow 的 pull request，可以選擇由哪個 kit 版本來評判它，因為 GitHub 執行的是 pull request 自己的 workflow 檔案。只有 layer 2 所要求的 code owner 核准能阻止它。一個待評估的緩解措施是 ruleset 規則「require workflows to pass」，它從固定的 repository 與 ref 執行 workflow（在 Team 方案上尚未驗證）。
- Reviewer 可能被它所 review 的文字說服而做出錯誤的結論。見第 6 節的「`agent-review` 的強度」。
- 測試結果由 pull request 的程式碼產生，可能被偽造。見第 6 節。
- Red-green 顯示 story 的測試在 main 上不通過。一個刻意寫成在 main 與 branch 上行為不同的測試，仍然可以滿足它。只有忠實度稽核能抓出這一點。
- 沒有硬性的保證說 story 的兩個語言版本意思相同。如果你核准的翻譯與 agent 所實作的英文不一致，只有 review agent 與你自己能抓出來。
- 哪些檔案算作依賴變更，是 `[risk.t2] dependency_manifests` 中的一份清單。清單中沒有列名的技術堆疊的 manifest 或 lock 檔案，在專案加入之前都不是 T2。`high_risk` 與專案自己的目錄結構也是如此。
- 對於由留言啟動或在本地 sandbox 中執行的 review，停留在指名的 commit 上是 prompt 中的一項指示，不是檢查。
- Actions 用量是估計值。它可能與帳單不同，所以 brief 中的警告可能太早或太晚出現。
- 溢出是關閉的。當 Actions 額度用盡時，CI 停止，在下個月開始或你付費購買更多額度之前，沒有任何東西能 merge。

**Layer 4，conductor**

- 它在一台 Mac 上執行。另一台 Mac 上為同一個專案的第二個 conductor 不受支援，也沒有任何機制偵測它。當 Mac 睡眠時，沒有任何事會推進。
- 暫停只有在 conductor 下次執行時才會撤回 auto-merge。在那之前，GitHub 仍會在已開啟 auto-merge 的 pull request 的 check 轉為綠色時就立即 merge 它。若要立即停止，也請手動關閉：`gh pr merge NUMBER --disable-auto`。
- 撤回 auto-merge 需要一次能列出 pull request 並呼叫 GitHub 的 pass。如果 GitHub 的 API 整個失效，就不會撤回任何東西，手動指令是唯一的辦法。
- GitHub 會在之後的 push 之間保留 auto-merge 請求。當 pull request 不再符合條件時，conductor 會在它的下一次 pass 撤回，但在 push 與那次 pass 之間，該請求仍是有效的。GitHub 仍然要求新的 commit 通過全部五個必要 check，而且 `risk-gate` 會讓 T2 commit 失敗，直到有人核准。所以這個空窗能放行的，是等級高於已啟用等級、但低於 T2 的 commit（只啟用 T0 時的 T1），而且它還要在 conductor 執行之前就通過 `ci`、`spec-verify` 與 `agent-review`。
- `touches` 是預測，會有遺漏。代價是 merge 衝突與重工，事後由 triage 修正。它不會導致錯誤的程式碼被 merge。
- Dispatch 可能重複，但絕不會遺失。
