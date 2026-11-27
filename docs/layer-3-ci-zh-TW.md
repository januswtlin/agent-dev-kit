# Layer 3：CI gates

*English: [layer-3-ci.md](layer-3-ci.md)。兩份內容不一致時以英文版為準。*

這一層在 branch 與 `main` 之間放了五項檢查：`ci`、`security`、`spec-verify`、`risk-gate` 與 `agent-review`。kit 持有 workflow（位於 kit 的 `.github/workflows/` 中的 reusable workflow）。專案持有精簡的 caller workflow（`agentdev-*.yml`，它們指名一個 kit 版本），以及一個檔案 `agentdev.toml`，裡面放有各項檢查讀取的每一個設定。這一層給你機械式的證明：每個核准的 test case 都對應到一個執行過且通過的測試；story 的測試在變更之前失敗、之後通過；更動 guardrail 或高風險程式碼的變更要等人來處理。它不提供讓這些檢查成為必要條件的規則（layer 2）、撰寫程式碼的 agent 的隔離（layer 1），也不提供分派工作的程式（layer 4）。這些檢查不需要 layer 1 與 layer 4 也能執行。沒有 layer 2 時它們只會回報：沒有任何東西讓它們成為必要條件。設計與理由在 [guideline-zh-TW.md](guideline-zh-TW.md)。

這裡的一切都尚未對真實的 GitHub 執行過。任何標為 **To verify** 的內容，描述的是程式碼所依賴的 GitHub 本身的行為。

## 1. 這一層保護什麼

| Check | What it verifies | Judged by |
|---|---|---|
| `ci` | Lint（`spec-lint`、`docs-lint`、`codeowners --check`、`pins`，以及你的 `lint_cmd`）與所有測試 | 程式 |
| `security` | 掃描 secret（gitleaks）與靜態分析（semgrep） | 程式 |
| `spec-verify` | 可追溯性：每個核准的 test case 都有一個執行過且通過的測試，而且已通過的測試不得消失。Red-green：story 的測試在 base branch 上失敗，在該 branch 上通過 | 程式 |
| `risk-gate` | 變更的風險等級。T2 需要人核准目前的 commit | 程式與人 |
| `agent-review` | 由另一個 agent 對實作，以及測試貼合程度，所做的 review | agent |

這些檢查所防範的：

- 通過卻什麼都沒測的測試（`assert True`）：red-green 會讓它失敗，因為它在 base branch 上也會通過。
- 被宣稱但沒有寫、被略過，或只在註解中提到的 test case：可追溯性讀取的是測試執行器自己的報告，不是原始碼。
- 連同 spec 一起被悄悄刪除的 test case：除非列在 `retired.toml`（由人核准）中，否則不允許消失。
- 放寬判斷它的規則的 pull request：`spec-verify` 與 `risk-gate` 的設定取自 base branch，kit 取自所釘選的版本，絕不取自 pull request。
- 變更 guardrail、高風險路徑、依賴 manifest，或過大的 diff，只憑綠燈檢查就通過：它是 T2，需要一個人。

它們不防範的在第 6 節。最重要的限制：測試結果是由 pull request 自己的程式碼產生的，所以 agent 可能寫出假的結果檔。最弱的檢查是 `agent-review`，因為 reviewer 讀的是不可信的文字。沒有任何硬性保證建立在它之上。

## 2. 開始之前

- Layer 2 是讓這些檢查成為必要條件，以及 `conductor` 環境所在之處。請先做它，否則下面的檢查只是建議性的。`agent-review` 的設定需要那個環境：[layer-2-github-zh-TW.md](layer-2-github-zh-TW.md)。
- kit 已安裝在你的 Mac 上，且 `agentctl` 可以執行（[adopting-zh-TW.md](adopting-zh-TW.md)）。`agentctl init` 會建立 caller workflow 與 `agentdev.toml`，並填入 kit 版本。
- kit 的 repository 必須不需憑證即可讀取。每個 reusable workflow 都以 `curl` 從 `codeload.github.com` 在釘選的 commit 取得 kit，不帶 token。不支援私有的 kit repository。（已知限制。）
- 專案已啟用 GitHub Actions。Workflow 分鐘數會計費（3.8 節）。
- 你的測試可以寫出 JUnit XML。如果不能，請在繼續之前選一個可以的執行器（3.3 節）。
- Story id 已決定：`[stories] id_digits` 預設為 3，並決定每個 id 的形式（`TC-012-03`、branch `story/012-slug`）。既有 issue 或 pull request 編號很大的專案可能想用 4。請在第一個 story 之前更改，不要在之後。

## 3. 設定

### 3.1 Caller workflow

`agentctl init` 把這些檔案從 `templates/project/.github/workflows/` 複製到專案中。每一個都呼叫 kit 中用途相同的 workflow。

| Caller file | Job | Check names GitHub reports | Runs on |
|---|---|---|---|
| `agentdev-ci.yml` | `ci` | `ci / ci`, `ci / spec-verify` | 進入 `main` 的 pull request（opened、synchronize、reopened、ready_for_review），以及 push 到 `main` |
| `agentdev-security.yml` | `security` | `security / security` | 同樣的事件 |
| `agentdev-risk-gate.yml` | `risk-gate` | `risk-gate / risk-gate` | 同樣的 pull request 事件，以及已提交或已撤銷的 review |
| `agentdev-agent-review.yml` | `agent-review` | commit status `agent-review` | 由 conductor 啟動（`workflow_dispatch`），以及已提交的 review（供 bridge 使用，3.7 節） |
| `agentdev-evidence.yml` | `evidence` | none | pull request 關閉並進入 `main`：把 AC、TC、測試、結果的表格貼到 story 的 issue 上 |
| `agentdev-brief.yml` | `brief` | none | 每日，加上每週一的摘要：Director 的 brief，以及 Actions 預算估計 |
| `release.yml` | `release` | none | 一個 `v*` tag。這是專案自有的範本，不是 kit 的 workflow：請填寫它的 deploy 區塊 |

GitHub 把被呼叫的 job 命名為 `<caller job> / <job>`。這就是為什麼必要的檢查是 `ci / ci` 而不是 `ci`。不要重新命名 caller job（`ci`、`security`、`risk-gate`）：ruleset 指名它們，release 範本指名它們，而 conductor 讀取檢查時會去掉 caller 的部分。`agent-review` 這個 status 是 commit status，所以沒有前綴。

`spec-verify` 讀取 `main` 上 `agentdev-ci.yml` 較早的執行，來找出不得消失的 test case。如果你重新命名那個檔案，歷史就無法再對應，`spec-verify` 會警告沒有東西可比較。

caller 有兩個固定事實：

- `agentdev-brief.yml` 與 `agentdev-agent-review.yml` 的 `agent-review` job（conductor 分派的 review）使用 `secrets: inherit`。它們需要 `conductor` 環境的 secrets，被呼叫的 job 因為宣告了 `environment: conductor` 而取得這些 secrets。同一個 caller 的 `review-bot` job（在已提交的 review 上執行）不傳遞任何 secret：對那個事件，GitHub 執行的是 pull request 的那份檔案。模型 token 請放在 `conductor` 環境中，絕不要放成 repository secret。（**To verify**：被呼叫的 job 中的環境 secrets。）
- 每個 caller 都兩次指名 kit，一次是 `uses: januswtlin/agent-dev-kit/.github/workflows/x.yml@<sha>`，一次是 `kit_version: <sha>`。兩者都必須等於 `agentdev.toml` 中的 `[kit] version`。

隨時檢查釘選：

```bash
agentctl pins
```

當 caller 指名了另一個 SHA、只指名一次，或 `[kit] version` 不是完整的 40 個字元的 SHA 時，它會失敗。它也在 `ci` 的 lint 步驟中執行，所以只改了一個 SHA 而沒改其他的 pull request 會失敗。

如果專案已有同名的 workflow 檔案，`agentctl init` 會保留它們並列出來。請手動合併，並保留上面的 job 名稱。

### 3.2 必要的檢查與第一次綠燈執行

五項必要的檢查放在它們自己的 ruleset `main-checks` 中，這是 ruleset 中屬於 layer 3 的那一半。Layer 2 用 `agentctl rulesets 2` 套用 `main`、`main-merge` 與 `tags`；layer 3 以 admin 身分，在專案內套用 `main-checks`：

```bash
agentctl rulesets 3
```

在新的 repository 上順序很重要：只有在 caller workflow 已在預設 branch 上且執行過一次，而且 `ci` 在 `main` 上已是綠燈之後，才套用它。從未回報過的檢查，無法以能讓任何東西 merge 的方式被要求。ruleset 啟用之後，pull request 需要全部五項。用 `gh api repos/OWNER/REPO/rulesets --jq '.[].name'` 確認：現在它應該也列出 `main-checks`。

`main` 上第一次 `ci` 的執行會建立基準，`spec-verify` 之後拿它來比較。在 `main` 上有一次執行上傳了結果之前，`spec-verify` 只會警告「no ci run on main has results; nothing to compare against」。結果在 90 天後過期；比較使用 `main` 上仍有結果的最新最多五次執行。

### 3.3 為你的技術堆疊設定 `[tests]`

workflow 不呼叫 `make`。它們讀取 `agentdev.toml`：

```toml
[tests]
setup_cmd = ""
lint_cmd = "make lint"
test_cmd = "make test"
junit_glob = "reports/junit/*.xml"
test_paths = ["tests/**", "**/tests/**", "**/__tests__/**", "**/*_test.*", "**/*.test.*", "**/*.spec.*", "**/test_*.py"]
```

| Key | Meaning |
|---|---|
| `setup_cmd` | 安裝依賴。在測試之前執行，在為 red-green 準備的乾淨 base branch checkout 中也會執行。如果它在那裡失敗，red-green 就失敗：無法執行的測試什麼也證明不了 |
| `lint_cmd` | 靜態檢查。由 `ci` 在 kit 自己的 lint 之後執行，也由 agent 在 push 之前執行 |
| `test_cmd` | 必須執行每一個測試，把 JUnit XML 寫到 `junit_glob` 找得到的地方，並在有測試失敗時以非零狀態結束。以 `bash -c` 執行 |
| `junit_glob` | JUnit 檔案所在之處。`agentctl collect-junit` 會把它找到的複製到一個目錄中，所以任何佈局都可以。符號連結會被略過 |
| `test_paths` | red-green 複製到 base branch 上的檔案，另外還有任何提到該 story 的 TC id 的檔案 |

更改 `agentdev.toml` 是 T2（永遠是 guardrail）。其他設定在 kit 的 `tools/agentctl/defaults.toml` 中。印出其中任何一項的有效值：

```bash
agentctl config tests.test_cmd
```

JUnit 輸出的起點（隨附的 `Makefile` 也列出了它們）：

| Stack | `test_cmd` |
|---|---|
| Python, standard library (the shipped default) | `agentctl junit-unittest tests reports/junit/unittest.xml` |
| pytest | `pytest --junitxml=reports/junit/python.xml` |
| vitest | `vitest run --reporter=junit --outputFile=reports/junit/web.xml` |
| Node's test runner | `node --test --test-reporter=junit --test-reporter-destination=reports/junit/node.xml` |
| Go | `gotestsum --junitfile reports/junit/go.xml ./...` |

兩條會咬人的規則：

- 測試必須能在乾淨的 GitHub-hosted runner 上執行，該 runner 有 Python 3.12，而且在測試之前只執行 `setup_cmd`。把測試需要的一切都放進 `setup_cmd`。
- Red-green 在 base branch 上執行 story 的測試，而那裡功能還不存在。測試必須以在自己的報告中回報失敗或錯誤的方式失敗。完全沒有執行的測試（執行器在回報之前就結束），只有在報告中含有屬於 story 其中一個測試檔的失敗或錯誤時才被接受為 red（以檔案不含副檔名的名稱比對）。如果你的執行器在測試檔無法 import 時什麼都不回報，請在依賴它之前，先用一個玩具 story 測試那種情況。

對於已有測試套件的專案，請保留測試名稱。可追溯性只要求 TC id 出現在測試的名稱、類別名稱或檔名中的某處。哪些形式算數見 3.4 節。

### 3.4 可追溯性：TC id 與測試名稱

核准的 story 有一個 `spec.toml`，含驗收條件（`AC-012-1`）與 test case（`TC-012-03`）。測試在它的名稱、類別名稱或檔名中帶有它的 TC id。許多語言禁止在識別字中使用 `-`，所以對於 story 012、case 03，以下這些都算數：`TC-012-03`、`tc_012_03`、`TC01203`、`TC 012 03`。這個比對模式不分大小寫，並依循 `[stories] id_digits`。

範例：

```python
def test_tc_012_03_after_passing_the_order_is_paid(self): ...
```

```js
test("TC-012-03 after passing, the order is paid", () => { ... });
```

什麼算通過：

- 執行器的報告說該測試執行過且通過。被略過的測試、缺少的測試，以及只出現在註解中的 TC id，都不算。
- 在隨附的 unittest 執行器中，被標為 `expectedFailure` 且其斷言失敗的測試，會被回報為 skipped，所以它永遠不算通過的 test case。
- 在 `main` 上通過過的 TC（在最新五次有結果的執行中的任何一次）必須仍然通過。唯一能放掉它的方法，是把它列在 specs 目錄下的 `retired.toml` 中（`retired = ["TC-012-03"]`）。該檔案受 CODEOWNERS 與 `human_gated` 保護。

Story 有兩個語言檔案（`story.md` 為英文，`story-<lang>.md`，其中 `<lang>` 是 `[stories] translation`，預設 `zh-TW`）。`spec-lint` 檢查兩者有相同的 AC 與 TC id、順序相同、章節相同，並且它們在 pull request 中一起更改。設定 `translation = ""` 即只用英文。`max_lines`（預設 80）限制每個 story 檔案的行數。

當設定了 `[docs] translation` 時，文件以同樣方式檢查：每個 `<name>.md` 都需要有標題相同的 `<name>-<lang>.md`，而且 `[docs] required` 中的檔案必須存在。預設為關閉。

### 3.5 風險等級

`risk-gate` 根據更動的路徑計算出一個等級，路徑以 `git diff -z` 讀取，使用 base branch 上現有的 `agentdev.toml`。

| Tier | When | What it needs |
|---|---|---|
| T0 | 每個更動的檔案都符合 `[risk.t0] paths`（預設 `docs/**`、`**/*.md`、`LICENSE`） | 綠燈檢查 |
| T1 | 在 story branch（`story/NNN-slug`）上的程式碼變更，且沒有觸發任何 T2 的理由 | 綠燈檢查與 `agent-review` |
| T2 | `[risk.t2]` 的 `guardrails`、`human_gated`、`high_risk` 或 `dependency_manifests` 中的任何檔案；超過 `[risk.thresholds]` 的 diff；或在不屬於任何 story 的 branch 上的程式碼變更 | `[roles] humans` 中的一個人核准目前的 commit |

測試檔不是 T0：削弱測試就是行為的改變。`.github/**` 與 `agentdev.toml` 永遠是 guardrail，不論專案怎麼寫，而且 T2 永遠不能列入 conductor 的 `auto_merge_tiers`。

請把 `high_risk` 設成專案實際的佈局。預設清單（`**/auth/**`、`**/payments/**`、`**/billing/**`、`**/migrations/**`、`infra/**`、`**/*.tf`、`**/Dockerfile`、`**/docker-compose*.yml`）只是個開始。`agentdev.toml` 中的清單會整個取代預設值，所以請複製你想保留的條目。`dependency_manifests` 也一樣：請為你自己的技術堆疊擴充它，包括 lock 檔與 registry 設定。

```toml
[risk.t2]
high_risk = [
  "**/auth/**",
  "**/payments/**",
  "**/migrations/**",
  "infra/**",
  "**/Dockerfile",
  "app/security/**",
]
```

`risk-gate` 會把等級發布兩次：pull request 上的 label `tier:T0`、`tier:T1` 或 `tier:T2`，給人看；以及 head commit 上的 commit status `risk-tier/T0`、`risk-tier/T1` 或 `risk-tier/T2`，描述為「pull request #N into BRANCH」。conductor 讀的是 status，因為 agent 的 token 可以編輯 label，但不能寫 commit status，而且只有當描述說明該等級是針對那個 pull request 進入預設 branch 計算出來的，conductor 才相信它。沒有這種 status 的 commit 算作 T2；有多個時，取最嚴格的。

在 story branch 之外，`risk-gate` 會把 `agent-review` 設為 success，描述為「not a story branch; no agent review required」，所以必要的 status 在那裡得到滿足。文件（T0）不需要 agent review，其他任何非 story 的變更是 T2，由人來 review。

對於 base 不是預設 branch 的 pull request，`risk-gate` 會失敗，而不是被略過。被略過的 job 對必要的檢查而言算通過，而如果 pull request 被重新指定目標，那個結果會留在 commit 上。

草稿 pull request：`ci` 只執行 lint，`risk-gate` 執行，而 `security` 與 `spec-verify` 被略過。GitHub 把被略過的檢查顯示為通過。這只有在草稿不能被 merge，而且把它標為 ready（`ready_for_review`）會在同一個 commit 上啟動完整的執行時，才可以接受。Layer 2 的檢查表涵蓋了 ready-for-review 這一步。

### 3.6 在玩具 story 上測試這些 gate

在處理真正的 story 之前，先用一個小 story 執行 gate 一次：一個 AC、兩個 TC，先有一個失敗的測試，再有實作。與 conductor 的完整流程是 [layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md) 中的 spike。若只要演練這一層，請為 spec 已在 `main` 上的 story push 一個 branch `story/NNN-slug`，自己開啟 pull request 並把它標為 ready。先把它開成草稿，以便看到草稿上只有 lint。

期望：只 push 測試檔的第一次 push，會讓 `spec-verify` 通過 red 的部分（它的測試在 base branch 上失敗），並讓可追溯性失敗（測試在該 branch 上也失敗）。實作之後，`ci / ci`、`ci / spec-verify` 與 `security / security` 全是綠燈，而 `risk-gate / risk-gate` 在 T0 或 T1 時是綠燈，在 T2 時是紅燈，直到列名的人核准。

### 3.7 `agent-review`

必要的 status `agent-review` 由兩個來源之一設定。

**Claude，作為 workflow。** conductor 針對 story 的 pull request 的某一個 commit 分派 `agentdev-agent-review.yml`（輸入為 `pr`、`story`、`developer`、`sha`）。`claude` job：

- 只從預設 branch 執行，並使用 `conductor` 環境，該環境的 deployment 規則只允許預設 branch，所以 branch 無法執行它或讀取它的 secret；
- 檢查 pull request 是開啟的、來自這個 repository 並以預設 branch 為目標，而且它的 head 就是 conductor 所詢問的 commit。如果 branch 移動了，就不 review 任何東西，也不發布任何東西。conductor 的下一次輪詢會針對新的 commit 再問一次；
- 把預設 branch checkout 為 reviewer 自己的工作目錄，並把 pull request 以資料的形式放在旁邊的 `./pr` 中，所以 pull request 無法提供 Claude Code 的設定或 hook；
- 從 kit 在釘選版本的 `review` prompt 讀取它的指示，內容依 `agentdev.toml` 填入；
- 以唯讀 token 與 `--tools "Read,Grep,Glob,Write,Bash"` 執行，Bash 只預先核准三個唯讀的 `git -C pr` 指令，並把它的結論寫在 runner 的暫存目錄下。

另一個 `publish` job 從不看到 pull request 的檔案，它把發現的問題以留言貼出，並設定 status。只有在 review 步驟本身成功時，結論才算數。沒有完成的 review 會被發布為 failure，絕不留在 pending 或被當作通過。

設定：

1. `conductor` 環境存在，並有它的 branch 規則（[layer-2-github-zh-TW.md](layer-2-github-zh-TW.md)）。
2. 建立 review token。在 Claude Code 已登入的 Mac 上，產生一個長效的 OAuth token（`claude setup-token`），並把它存為 `conductor` 環境的環境 secret `CLAUDE_CODE_OAUTH_TOKEN`：

```bash
gh secret set CLAUDE_CODE_OAUTH_TOKEN --env conductor
```

3. 對於 sprint 檔案指派給某位具名開發者的 story，請改用加上後綴的名稱存放那個人的 token：`CLAUDE_CODE_OAUTH_TOKEN_<LOGIN>`，login 為大寫，其他每個字元都換成 `_`（`CLAUDE_CODE_OAUTH_TOKEN_ALICE`）。不加後綴的名稱只用於 `default` 的 story。對於具名開發者，它絕不是備援。

在你 Mac 上執行的 conductor 看不到 GitHub 的 secrets，所以它在分派之前無法檢查 token 是否存在。token 缺少時，workflow 會啟動，review 步驟失敗，而 `publish` 把該 commit 上的 `agent-review` 設為 failure。如果 review 立刻失敗，請看那次執行。

`anthropics/claude-code-action` 的輸入，以及 `--tools` 與 `--allowedTools` 的效果，要在 spike 中驗證。（**To verify**。）

**Review bot，經由 bridge。** 另一個 agent 發布的 review（例如 Codex cloud 的 GitHub 整合，或來自本機 sandbox 的 review），會由 `bridge` job 在已提交的 pull request review 上轉成 status（由 caller 的 `review-bot` job 呼叫，不帶 secrets）。它只聽取 repository 變數 `REVIEW_BOTS` 中的 login，這是一個 JSON 陣列：

```bash
gh variable set REVIEW_BOTS --body '["chatgpt-codex-connector[bot]"]'
```

當 review 的狀態是 `approved`，或它的內文含有 `agent-review: pass`（不分大小寫）時，status 為 success，否則為 failure。status 寫在該 review 所提交的 commit 上。

如果 review 的 stage 在本機 sandbox 中執行（`[roles.harness.<name>]` 中是 `via = "sbx"` 而沒有 `review_workflow`），sandbox 的 token 無法寫 status，所以 review 是以開發者的 agent App 發布的 pull request review。把那個 App 的 login（`NAME-agent[bot]`，或你的 App 的 slug 給出的任何名稱）加進 `REVIEW_BOTS`，否則該 review 會被忽略。請記下你在 review 上實際看到的 login。Codex 整合的 login 在 spike 之前只是猜測。（**To verify**。）

如果 review 是在一般的雲端 session 中完成，reviewer 與實作者可能是同一個 GitHub 身分，無法區分。prompt 告訴 reviewer 要 review 哪個 commit，並在 head 不同時停止。那是對 agent 的指示，不是強制執行。

哪些 reviewer 在哪個 stage 執行，以及順序，設定在 `[roles.developers.<login>.stages]`；見 [layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)。只有一個人、一家廠商的專案，會以同一個 harness 的全新 session 作為 reviewer。在那種情況下，主要的保證由機械式檢查提供。

### 3.8 Actions 分鐘數與預算

GitHub 以金錢計算 Actions 的費用（撰寫本文時 Team 方案每月有 $18 的額度；請查看 GitHub 的頁面），並把每個 job 無條件進位到整分鐘。設計上讓用量保持低：

- 測試套件在 head 上執行一次，story branch 另外在 base 上再執行一次，都在同一個 job 中。
- 草稿只執行 lint。每個 story 大約三次完整的 gate 執行，而不是每次 push 都一次。
- `spec-verify`、`risk-gate`、`evidence`、`brief` 與 `agent-review` 的 publish job 不執行 pull request 的程式碼，可以使用較小的 runner：把 repository 變數 `LIGHT_RUNNER` 設為它的標籤。如果沒設，它們使用 `ubuntu-latest`。
- conductor 在你的 Mac 上執行，所以不使用分鐘數。

每日的 brief 會執行 `agentctl budget`，它根據 job 紀錄估計當月用量，存在 repository 變數 `ACTIONS_USAGE` 中，並印出一行讓 brief 顯示。你也可以自己執行它：

```bash
agentctl budget --dry-run
```

這個估計可能與帳單不同。GitHub 的帳務頁面才是準據。

Overflow 是關閉的。`[conductor.actions] overflow_runner` 刻意留空：`ci` 與 `security` 會執行 pull request 的程式碼，所以 overflow runner 必須是專用的、不持有任何憑證，並且每個 job 都重新建立。開發者的 Mac 以及 agent 工作所在的任何 VM 都不是這樣。額度用完時，CI 會停止，直到下個月或你付費購買更多之前，任何東西都無法 merge。（**To verify**：到那時 GitHub 會怎麼做。）如果你確實設定了合適的 runner，超過 `overflow_at`（額度的 0.85）的用量會把 repository 變數 `CI_RUNNER` 指向它，新的月份會把它改回來。只有 `ci` 與 `security` 遵循 `CI_RUNNER`。做判斷的 job 永遠留在 GitHub-hosted runner 上。

guideline 中每個 story 的分鐘數數字是估計值。在 spike 中，請記錄真實的數字：你的測試執行一次所需的分鐘數、每個 story 的完整 gate 執行次數，以及 GitHub 的 Actions 用量頁面為該 story 顯示的分鐘數。

### 3.9 升級釘選的 SHA

一個 pull request 更改每一處指名 kit 的地方：

1. 在 Mac 上，從 kit 在該 commit 的 clone，以完整的 commit SHA 安裝新版本：

```bash
./install.sh NEW_SHA
```

2. 在 `chore/` branch 上，把 `agentdev.toml` 的 `[kit] version` 與每個 `agentdev-*.yml`（每個檔案兩處：`uses:` 與 `kit_version:`）中的舊 SHA 換成新的。
3. 執行 `agentctl pins`。用新版本執行，不要用舊版本：在釘選進入 `main` 之前，把 `AGENTDEV_KIT_VERSION` 設為新的 SHA。

```bash
AGENTDEV_KIT_VERSION=NEW_SHA agentctl pins
```

4. 開啟 pull request。它更動了 `.github/**` 與 `agentdev.toml`，所以是 T2：要有一個人核准，而且 CODEOWNERS 讓那個核准成為必要。請讀第 6 節的限制：對於修改 caller 的 pull request，實際執行的 workflow 檔案是 pull request 自己的，所以它的檢查結果說明不了多少。保護你的是那個人的核准。
5. merge 之後，在每一台其他處理這個專案的 Mac 上執行 `./install.sh NEW_SHA`。啟動器從預設 branch 讀取釘選，所以尚未安裝新版本的 Mac 會停止，並顯示「kit NEW_SHA is not installed」以及要執行的指令。

在你核准之前，請閱讀兩個 SHA 之間 kit 的變更。新的 kit 版本會改變判斷你 pull request 的東西。

## 4. 檢查表

設定完成時執行一次，並在你更改 workflow、`agentdev.toml` 或 kit 版本之後再執行。**大多數項目是嘗試做一件必定失敗的事。** 如果這樣的嘗試成功了，就表示某一道防線沒有發揮作用。少數項目檢查正常路徑是否運作，並期望成功：D1 與 D16（後者在 [layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)）。D21 有一部分期望成功。「Expected」欄會說明是哪一種。

請在「Result」欄記下你實際看到的訊息。這些項目沒有一項對真實的 GitHub 執行過，所以不同的結果也可能表示這份檢查表是錯的。也請把那一點寫回來。項目 id 與其他 layer 文件共用，且絕不重複使用。D9、D10 與 D23 在 [layer-2-github-zh-TW.md](layer-2-github-zh-TW.md)；D16、D20 與 D22 在 [layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)。

除非項目另有說明，測試用的 pull request 以 `main` 為目標。

| # | Attempt | Expected | Result |
|---|---|---|---|
| D1 | 一個只更改 `docs/guideline.md` 的 PR。自己開啟它，從名稱不以 `story/`、`spec/`、`sprint/` 或 `chore/` 開頭的 branch | 標為 T0，檢查是綠燈，且 `agent-review` 設為 success，並附「not a story branch」。沒有任何東西會自動 merge 它。這一項應該成功。再從 `chore/` branch 重做一次，由 conductor 開啟 pull request：結果相同，且 conductor 絕不 merge 它 | |
| D2 | 更改 `agentdev.toml` 並清空 `[risk.t2] high_risk` | 標為 T2（`agentdev.toml` 是 guardrail）；沒有人的核准就不能 merge。而且這個 PR 的等級是以 `main` 上的設定計算的 | |
| D3 | 在不是 story branch 的 branch 上更改程式碼 | T2，理由是沒有對應的 story | |
| D4 | 加入一個依賴 | T2，理由是 `dependency_manifests` | |
| D5 | 在 story branch 上，加入一個帶有 TC id 的 `assert True` 測試 | `spec-verify` 失敗，訊息指出該 TC 在 base 上已經通過 | |
| D6 | 在 story branch 上，漏掉一個 TC | `spec-verify` 失敗並說出缺的是哪一個 | |
| D7 | 把某個 TC 的測試標為 skip | `spec-verify` 失敗。只在 base 上被略過的測試，也不被接受為 red | |
| D8 | 修改已核准的 `spec.toml`，並刪除一個在 `main` 上通過的 TC，連同它的測試 | 需要人的核准才能 merge（`human_gated`）。而且 `spec-verify` 失敗，說該 TC 在 base 上通過但現在缺少。唯一能放掉它的方法是把它列在 `retired.toml` 中，這也需要核准 | |
| D11 | 只更改 `story.md` 而不更改翻譯的 story 檔案（或反過來） | `ci` 失敗 | |
| D12 | 在兩個 story 檔案中各放一個意思不同的 AC（例如一個寫 10 MB，另一個寫 5 MB） | review agent 指出差異並視為 blocking。這一項是軟性控制；請記下它是否真的被抓到 | |
| D13 | 當 story 的 PR 仍是草稿時 | `ci` 只執行 lint，`risk-gate` 執行，而 `security` 與 `spec-verify` 被略過。GitHub 把被略過的檢查顯示為通過；PR 仍然不能 merge，因為它是草稿（[layer-2-github-zh-TW.md](layer-2-github-zh-TW.md) 中的 D23） | |
| D14 | 開啟一個 base 是 `main` 以外的 branch 的 PR（例如從 `story/000-example` 到 branch `test/base`） | 它上面沒有出現 `ci`、`security`、`spec-verify` 或 `risk-gate` 檢查，也沒有 `tier:` label。針對另一個 base 取得的 status 不可以存在。如果在它上面提交了 review，`risk-gate` 會出現，而且是紅燈（D19） | |
| D15 | 一個只更改 lock 檔的 PR（例如 `package-lock.json` 或 `uv.lock`）。再用設定中沒有列名的 lock 檔重做一次，例如 `composer.lock` | 標為 T2，理由是 `dependency_manifests`；沒有人的核准就不能 merge | |
| D17 | 故意讓 Claude review 失敗：把 `conductor` 環境的 secret `CLAUDE_CODE_OAUTH_TOKEN` 設成無效的值，然後針對一個開啟中的 story PR 執行 `gh workflow run agentdev-agent-review.yml -f pr=N -f story=NNN`。如果你以 `_LOGIN` 後綴存放該 secret，就改那一個，並加上 `-f developer=LOGIN_IN_UPPER_CASE`。之後還原該 secret | PR 的 head commit 上的 `agent-review` status 是 failure（「review requested changes or did not finish」）。絕不是 success，也不會留在 pending | |
| D18 | 惡意的結果 artifact。在測試用的 story branch 上，讓測試步驟在 `reports/` 內留下一個符號連結：例如一個測試檔，在被 import 時執行 `os.symlink("/etc/hostname", "reports/junit/link.xml")`。把 PR 標為 ready，讓完整的 gate 執行。再重做一次，這次把 `reports` 本身換成指向另一個目錄的連結 | `spec-verify` 在「Keep only plain result files」這一步失敗，說明該目錄含有符號連結。base checkout（`base/`）下的任何東西都沒有被更改。如果連結沒有在上傳後留存，而是以一般檔案抵達，這一步不會失敗：請記下實際抵達的是什麼（**To verify**：artifact 的上傳與下載如何處理連結） | |
| D19 | 重新指定目標。從 `main` 建立 branch `test/base`。從 story branch 開一個進入 `test/base` 的 PR，並在上面提交一個 review。然後在不 push 任何東西的情況下，把 PR 的 base 改為 `main`。之後再 push 一個 commit | review 之後：該 commit 上的 `risk-gate` 是紅燈，訊息為「this pull request targets test/base, not main」。它是失敗，不是被略過。重新指定目標之後、尚未 push：PR 被阻擋，沒有任何東西被記功。`risk-gate` 仍是紅燈，而 `ci`、`security` 與 `spec-verify` 沒有結果，因為這些 workflow 不會在 base 變更時執行。push 之後：每個必要的檢查都針對 `main` 執行。請記錄這三個時間點各發生了什麼（**To verify**） | |
| D21 | Review 與移動中的 head。在分派的 `agentdev-agent-review.yml` 執行的 `claude` job 仍在排隊時，對 story branch push 一個新 commit。要以手動方式得到同樣的情況：`gh workflow run agentdev-agent-review.yml -f pr=N -f story=NNN -f sha=PREVIOUS_HEAD_SHA`，如果 story 指名了開發者，就加上 `-f developer=LOGIN_IN_UPPER_CASE` | `claude` job 在「Resolve the pull request」停止，訊息為「the branch moved since this review was asked for」。`publish` job 被略過：沒有發現問題的留言，兩個 commit 上也都沒有 `agent-review` status。conductor 執行時，它的下一次輪詢會要求對新 head 做 review，而那個 review 會被發布。最後這一部分應該成功。同一個 head 可能出現重複的 review；如果看到，請記下來 | |
| D24 | 從某個 branch 執行 review。`gh workflow run agentdev-agent-review.yml --ref SOME_BRANCH -f pr=N -f story=NNN`。（workflow 檔案必須存在於那個 branch；請使用從 `main` 建立的 branch。） | `claude` job 被略過（它只從預設 branch 執行），或 `conductor` 環境拒絕給它 secrets。沒有 review 執行，也沒有 status 被寫入。如果 job 帶著 token 走到了 review 步驟，就表示環境的 branch 規則沒有發揮作用 | |
| D25 | 釘選檢查。在某個 branch 上，只更改其中一個 `agentdev-*.yml` 的某一行 `uses:` 中的 SHA，其他都不動 | `ci` 在 lint 失敗，來自 `agentctl pins` 的訊息指出檔案與兩個 SHA。再重做一次：改 `kit_version:` 而保留 `uses:`，以及只改 `[kit] version` | |
| D26 | Bridge。以不在 `REVIEW_BOTS` 中的帳號，然後以在其中的帳號，在 story PR 上提交 review，後者一次 approve、一次要求更改 | 不在清單中：不寫入 `agent-review` status。在清單中且 approve：被 review 的 commit 上 `agent-review` 為 success，「review bot approved」。在清單中且要求更改：failure。這部分應該成功。請記下你實際看到的 login | |
| D27 | 設定取自 base。在 story branch 上，編輯 `agentdev.toml` 的 `[tests] test_cmd` 讓它什麼都不執行，並編輯 `[risk.t2]` 讓 `high_risk` 是空的 | PR 是 T2，因為它更動了 `agentdev.toml`。`spec-verify` 與 `risk-gate` 使用 `main` 上的設定：沒有任何風險理由消失。`ci` 本身會執行更改後的 `test_cmd`（它本來就執行 PR 的程式碼），而 red-green 與可追溯性仍然失敗，因為沒有測試回報 | |
| D28 | pull request 樹中的惡意檔案。在 story branch 上，於 repository 根目錄加入一個名為 `json.py` 的檔案（以及一個名為 `agentctl.py` 的），和一個 `tomllib.py` | `risk-gate` 與 `spec-verify` 的行為和沒有它們時一樣：判斷用的步驟以 `-I` 啟動 Python，所以樹中無法提供模組。那些 job 中沒有執行任何來自該檔案的東西 | |

## 5. 尚未驗證

這一層裡沒有任何東西對真實的 GitHub 執行過。以下是程式碼依賴 GitHub 的行為或廠商的行為之處，也是最可能出現意外的地方：

- GitHub 為被呼叫的 workflow 所回報的檢查名稱（`ci / ci`、`ci / spec-verify`、`security / security`、`risk-gate / risk-gate`），以及 ruleset 能否以 Actions app 作為來源來要求它們。Layer 2 持有 ruleset；這裡的名稱必須與它完全一致。
- 被呼叫的 job 中的環境 secrets：caller 中的 `secrets: inherit` 是否把 `conductor` 環境的 secrets 傳給宣告了 `environment: conductor` 的 job。
- 由 bot 帳號啟動的 `pull_request_review` 事件，是否如 bridge 所預期地帶有該 review 的 `commit_id` 與狀態，以及 Codex review bot 的 login 與 review 格式。
- `anthropics/claude-code-action` 的輸入，`--tools` 是否限制 session 中存在的工具，以及 `--allowedTools` 是否只預先核准呼叫。
- `actions/download-artifact` 與 `upload-artifact` 如何處理惡意的封存檔與符號連結（D18）。
- commit status `risk-tier/*` 與 `agent-review` 是否出現在 pull request 的 check rollup 中（那是 conductor 讀取它們的地方），以及以 workflow token 寫入的 status 是否被接受為來自 Actions app。
- 在不 push 的情況下被重新指定目標的 pull request（D19），以及在不 push 的情況下被標為 ready 的草稿，會發生什麼事。
- 從 runner 以 SHA 從 `codeload.github.com` 取得 kit，以及釘選的 tarball 是否每次都是相同的位元組。
- 在你專案的規模下，這些檢查是否維持在 Actions 額度之內，以及額度用完時 GitHub 會怎麼做。
- 在你自己的技術堆疊上的 red-green：你的測試執行器如何回報一個在 base branch 上無法 import 的測試檔。
- semgrep 的設定 `--config auto` 需要 runner 能以網路連到 semgrep 的規則 registry，而 gitleaks 的下載需要 GitHub 的 release 主機。兩者都沒有執行過。

## 6. 已知限制

- **結果可以被偽造。** JUnit 檔案是由執行了 pull request 程式碼的 job 產生的，所以 agent 可以寫出假的報告。`spec-verify` 把這些檔案視為不可信的輸入（只接受一般的 `*.xml` 與 `collected.json`，符號連結會讓 job 失敗，解壓縮在兩個 checkout 之外），這保護的是判斷者，不是內容。防禦是受保護的建置設定（`agentdev.toml`、workflow）、review 對每個 test case 的稽核，以及定期的抽查。
- **Red-green 只顯示測試在 base 上失敗，不顯示為什麼。** 被寫成在 base 與在 branch 上行為不同的測試（例如檢查某個檔案是否存在）可以滿足它。只有 review 對每個測試的稽核才抓得到。
- **test case 的清單可能不完整。** 這些檢查證明每個核准的 TC 都有一個執行過的測試。它們不證明清單是完整的。那取決於 product-owner stage 的提問，以及你核准 story 時的閱讀。
- **`agent-review` 是最弱的檢查。** reviewer 讀的是不可信的文字（diff、commit 訊息、檔案），這些文字可以說服它做出錯誤的結論。隔離限制的是被誤導的 reviewer 能做什麼，不是它得出什麼結論。沒有任何硬性保證取決於它。
- **從 bot 或 sandbox 經 bridge 轉來的 review，只和 login 清單一樣可靠。** login 在 `REVIEW_BOTS` 中的任何人都可以把 status 設為 success。
- **基準只和 `main` 上的執行一樣好。** `spec-verify` 與 `main` 上結果可以讀取的最新五次執行比較，不論那些執行的結論是什麼。`main` 上不完整的執行仍然會縮小被記住的範圍，而從未出現在可讀取的執行中的 test case 無法被保護。
- **編輯 caller workflow 的 pull request，自己選擇判斷它的 workflow。** 對於 `pull_request` 事件，GitHub 執行的是 pull request 的 workflow 檔案。因此，更改 `uses:` 或 `kit_version:` 會決定由哪個 kit 版本（或 repository）產生該 pull request 自己的檢查結果。設定仍然取自 base branch，但程式碼不是。防禦是：`.github/**` 是 guardrail，由 CODEOWNERS 中的一個人擁有，所以不論檢查怎麼說，ruleset 都要求人的核准；以及你要閱讀每一個這類 pull request 的 diff。請把更改 `.github/**` 的 pull request 上的綠燈檢查視為沒有資訊量。一個值得評估的緩解措施是要求 workflow 必須通過的 ruleset 規則：它從固定的 repository 與 ref 執行 workflow，而不是 pull request 的副本（在 Team 方案上未驗證）。
- **kit 的 repository 必須是公開的，或以其他方式不需 token 即可讀取**，因為 workflow 以 `curl` 取得它。
- **被略過的必要檢查算作通過。** 設計依賴草稿無法 merge，以及 `ready_for_review` 會啟動完整的執行。如果在真實的 GitHub 上這兩者之一不成立，草稿可能憑被略過的結果而 merge。
- **Overflow 是關閉的**，所以當 Actions 分鐘數用完時，CI 會停止，任何東西都無法 merge。
- **分鐘數與費用的估計沒有經過測量。** `agentctl budget` 可能與帳單不同。
- **依賴是交給人處理，不是被掃描。** 新增或更改的依賴永遠是 T2。沒有任何檢查會看那個套件是否安全。
- **掃描器的設定取自樹中。** `.gitleaks.toml`、`.semgrepignore` 與類似的檔案是從 pull request 的 checkout 讀取的，所以它們是 guardrail（T2）。削弱它們的變更要等人來處理。
