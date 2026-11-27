# Layer 2: GitHub protection

*English: [layer-2-github.md](layer-2-github.md)。兩份內容不一致時以英文版為準。*

這一層讓 GitHub 本身拒絕 agent 或失誤不該能做的事：不經 pull request 變更 `main`、merge 自己的成果、核准自己的成果、移動 release tag，或從 branch 讀取 pipeline 的 secret。它提供三個 ruleset（`agentctl rulesets 2`），以及在 layer 3 存在之後的第四個、要求它的檢查的 ruleset（`agentctl rulesets 3`），從 `agentdev.toml` 產生的 CODEOWNERS（`agentctl codeowners`）、`conductor` environment、Conductor GitHub App，以及幾項 repository 設定。它不執行任何檢查：`main-checks` ruleset 所要求的檢查來自 layer 3。它不啟動 agent：那是 layer 4。它與 [layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md) 搭配，這些規則就是針對該層的 agent token 所寫的。設計在 [guideline-zh-TW.md](guideline-zh-TW.md)；威脅在 [threat-model-zh-TW.md](threat-model-zh-TW.md)；採用 kit 的方式在 [adopting-zh-TW.md](adopting-zh-TW.md)。

每個專案做一次，由管理該 repository 的人執行。

## 1. What this layer protects

| Threat | Control |
|---|---|
| push 到 `main`、force-push、刪除 `main` | `main` ruleset：不可刪除、不可 non-fast-forward、只能透過 pull request 變更。任何人都沒有 bypass。 |
| 在需要人的地方，pull request 沒有人就被 merge | `main` ruleset：需要 code owner review。CODEOWNERS（從 `[risk.t2]` 產生）為護欄、spec、sprint、dependency manifest 與高風險程式碼指定 director。新的 push 會使過時的核准失效。 |
| agent merge 自己通過的綠燈 pull request | `main-merge` ruleset：只有 repository admin 與 Conductor App 可以更新預設 branch。agent token 可以 push branch，而且依 GitHub 的規則可以呼叫 merge endpoint，所以拒絕它的是這個 ruleset。 |
| gate 通過之前就 merge | `main-checks` ruleset（隨 layer 3 套用）：五個必要檢查，strict（branch 必須是最新的）。檢查來自 layer 3。 |
| agent 建立、移動或刪除 tag：`v*` release，或名稱像 branch 的 tag（`origin/main`），使簡短的 ref 名稱解析到它 | `tags` ruleset：只有 repository admin 能動任何 tag。 |
| branch 或雲端 session 讀取 pipeline 的 secret | `conductor` environment 持有它們，並且只允許預設 branch。 |
| agent 核准自己的 pull request | Conductor App 開啟 pull request，所以沒有任何人是作者；agent 的 token 無法以 code owner 的身分 review。人不能核准自己開啟的 pull request（D10）。 |
| squash-merge 歷史、過時的 branch | repository 設定：只允許 squash、自動刪除 head branch。 |

## 2. Before you start

- 一個使用能對私有 repository 強制執行 ruleset 的方案（Team 或更高）的 GitHub organization，每人一個席位。agent 與 Conductor App 是 GitHub App，不佔席位。在不強制執行 ruleset 的方案上，ruleset 會被建立但沒有任何保護：目前哪些方案名稱適用，尚未驗證，所以請查看 GitHub 的方案頁面。
- 以 repository admin 登入的 `gh`（`gh variable get --help` 必須印出用法說明；較舊的版本沒有它）、能透過 HTTPS push 的 `git`（`gh auth setup-git`）、Python 3.11 或更新版本，以及已安裝在這台 Mac 上的 kit（[layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)，第 2 節）。
- 專案的 repository 已存在，`main` 上有 `agentdev.toml`（至少有 `[kit]`、`[roles] directors` 與 `humans`）。`agentctl init DIRECTOR_LOGIN [OTHER_LOGIN ...]` 會建立它與 CODEOWNERS（[adopting-zh-TW.md](adopting-zh-TW.md)）。
- Layer 2 可以單獨運作。`agentctl rulesets 2` 套用 `main`、`main-merge` 與 `tags`，三者都不要求任何檢查。必要的檢查是另一個 ruleset `main-checks`，等 layer 3 的 caller workflow 已在 `main` 上並且執行過之後，由 `agentctl rulesets 3` 套用（第 3.4 節）。更早套用會擋住每一次 merge，因為從不回報的檢查永遠不會通過，而該 ruleset 沒有 bypass。
- 只要 `main` 上還是預留位置 `DIRECTOR_LOGIN`，就沒有人是 code owner，也沒有人能核准修正它的 pull request。在套用 ruleset 之前，請在 `agentdev.toml` 與 CODEOWNERS 中填入真正的 login。
- 你的 clone 要知道專案的預設 branch，因為 launcher 從它讀取 `agentdev.toml`。這個指令必須印出 `origin/main`；如果不是，請執行 `git remote set-head origin -a`：

```bash
git symbolic-ref --short refs/remotes/origin/HEAD
```

## 3. Setup

### 3.1 CODEOWNERS

CODEOWNERS 是產生的，不是手寫的。`agentctl codeowners` 從 `agentdev.toml` 的 `[risk.t2]` 與 `[roles] directors` 印出它；owner 是 director，而且只有人才是 owner（App 絕不是）。把它寫入、commit，並讓 layer 3 的 `ci` 在它偏離時失敗：

```bash
agentctl codeowners > .github/CODEOWNERS
```

```bash
agentctl codeowners --check
```

這個檔案涵蓋四個群組：`human_gated`（spec、sprint、產品文件）、`guardrails`（`.github/**`、`agentdev.toml`、agent 設定、`AGENTS.md`、掃描器設定）、`dependency_manifests` 與 `high_risk`。`[roles] directors` 不得為空。把 `agentdev.toml` 中的 `high_risk` 設成專案真正的結構，然後重新產生。

### 3.2 Conductor GitHub App

conductor 會開啟與 merge pull request、對 issue 留言與加 label、dispatch workflow、讀取檢查與 variable，並寫入 Actions 預算的 variable。在 organization 的 Settings > Developer settings > GitHub Apps 下建立一個 App：

- Repository 權限：Contents: Read and write；Pull requests: Read and write；Issues: Read and write；Actions: Read and write；Variables: Read and write；Checks: Read；Commit statuses: Read；Metadata: Read。
- 不訂閱任何 webhook，並取消勾選 Active。
- 產生一把 private key，並只安裝在這個 repository 上。記下 App 的數字 ID。把金鑰檔放在專案目錄之外（sandbox 會讀取那裡的每個檔案，包含被忽略的）。

這把金鑰用在兩個地方。在執行 conductor 的 Mac 上，它是 `conductor.env` 中指名的檔案（[layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)）。在 GitHub 中，它是下面的 environment secret，只由每日 brief job 讀取。

### 3.3 The `conductor` environment

1. 在 Settings > Environments 中，建立一個名稱剛好是 `conductor` 的 environment。
2. 在 Deployment branches and tags 下，選擇 Selected branches and tags，並新增一條只允許預設 branch（`main`）的規則。
3. 新增 environment secret `CONDUCTOR_APP_PRIVATE_KEY`，內容是金鑰的完整內容。或使用：

```bash
gh secret set CONDUCTOR_APP_PRIVATE_KEY --env conductor < PATH_TO_PRIVATE_KEY.pem
```

為什麼用 environment 而不是 repository secret：持有憑證的 job 會宣告 `environment: conductor`。從任何其他 ref 啟動的執行（包含手動 dispatch 某個 branch），GitHub 都會拒絕提供 secret。repository secret 沒有這種規則。

| Type | Name | Where | Value | Needed by |
|---|---|---|---|---|
| Environment secret | `CONDUCTOR_APP_PRIVATE_KEY` | Environment `conductor` | Conductor App 的 private key | 每日 brief（layer 3 的 caller，`agentdev-brief.yml`） |
| Environment secret | `CLAUDE_CODE_OAUTH_TOKEN`，或開發者自己的 `CLAUDE_CODE_OAUTH_TOKEN_LOGIN` | Environment `conductor` | 來自 `claude setup-token`；見 layer 3 | Claude review |
| Repository variable | `CONDUCTOR_APP_ID` | Settings > Secrets and variables > Actions > Variables | App 的數字 ID | 為空時略過 brief；最後才設定（第 3.5 節） |
| Repository variable | `CONDUCTOR_PAUSED` | 同上 | `true` 表示暫停，否則為 `false` 或不設定 | kill switch（[layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)） |

其他 variable（`REVIEW_BOTS`、`CONDUCTOR_QUOTA`、`LIGHT_RUNNER`、`CI_RUNNER`、`ACTIONS_USAGE`、`CONDUCTOR_BOT`）屬於 layer 3 與 4，在那裡說明。dispatch 憑證不再是 GitHub secret：它們放在 Mac 上的 `conductor.env`。

### 3.4 Rulesets

以 repository admin 身分執行，並帶上 Conductor App 的數字 ID（它會成為 `main-merge` 的 bypass actor）：

```bash
CONDUCTOR_APP_ID=APP_ID agentctl rulesets 2
```

沒有 `CONDUCTOR_APP_ID` 時腳本拒絕執行，而且它需要 `gh`。它依名稱建立或更新 kit 的 `templates/rulesets/` 中屬於 layer 2 的三個檔案：

- `main`：不可刪除、不可 force-push、只能透過有 code owner review 的 pull request 變更（其他情況需要核准的 review 數為零；push 時核准會失效；只允許 squash）。它本身沒有必要的檢查。任何人都沒有 bypass。
- `main-merge`：只有 repository admin（role 5）與 Conductor App 可以更新預設 branch。他們仍然要滿足 `main` 中的一切。
- `tags`：只有 repository admin 能建立、移動或刪除任何 tag。

確認：

```bash
gh api repos/OWNER/REPO/rulesets --jq '.[].name'
```

它必須列出 `main`、`main-merge` 與 `tags`。當 layer 3 的 caller workflow 已在 `main` 上並且執行過一次之後，套用檢查 ruleset（`main-checks`：五個必要檢查 `ci / ci`、`ci / spec-verify`、`security / security`、`risk-gate / risk-gate` 與 `agent-review`，strict，沒有 bypass）：

```bash
agentctl rulesets 3
```

要更改 ruleset，請改 kit 的範本，不是專案：範本是 kit 版本的一部分。

### 3.5 Repository settings

在 Settings > General > Pull Requests 中：開啟 Allow auto-merge、只允許 squash merging，並開啟 Automatically delete head branches。在 organization 的 Settings > Actions > General 中，確認 **Allow GitHub Actions to create and approve pull requests** 是關閉的。專案上的每個人都是 repository admin；agent 與 conductor 是 App。

Allow auto-merge 不是可選的：一旦 code owner 核准了 spec 或 sprint 的 pull request，conductor 在下一次 pass 就會對它啟用 auto-merge，無論 `auto_merge_tiers` 怎麼設定，因為這個決定是人做的。它絕不會對 `chore/` 的 pull request 這樣做。

最後，如果你要執行 conductor 與每日 brief，設定開啟 brief 的 variable。只能在第 3.3 與 3.4 節之後才做：

```bash
gh variable set CONDUCTOR_APP_ID --body APP_ID
```

### 3.6 Release tags

`tags` 使每個 tag 都只有 admin 能建立，所以 `v*` tag 是只有 admin 能給的 release 核准，而且沒有 agent 能 push 名稱像 branch 的 tag。專案自有的 `release.yml`（由 `agentctl init` 複製）在這樣的 tag 上執行，是個起點：它的 provider 區塊由你填寫，它的檢查名稱就是 kit 的必要檢查。雲端端應該只信任 `repo:OWNER/REPO:ref:refs/tags/v*`，這樣就沒有 branch build 或 agent session 能取得正式環境的存取權。`release.yml` 不是 kit 的 reusable workflow；更改它是 T2 變更。

## 4. Checklist

在 setup 完成時執行一次，並在你更改 ruleset、CODEOWNERS 或 kit 版本時再執行。使用以 `main` 為目標的測試 pull request。**大多數項目嘗試的是必須失敗或被拒絕的事。** 如果有一項成功了，就表示有一道防線沒有運作。預期成功（全部或部分）的項目：C17（它的最後一步）、D23 與 D25。請在 Result 欄記下你實際看到的訊息。這些項目都還沒有在真實的 GitHub 上執行過，所以不同的結果可能表示這份 checklist 有誤；也請把它寫回來。

標示「job」的項目，如 [layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md) 第 4 節所述使用 agent token：`agentctl sandbox job claude sprint STAGE "Run these commands ... and print their output: COMMANDS"`，push token 用 stage `impl`，review token 用 `review`，然後讀取 log。以 GitHub 顯示的為準。

### C. Agent tokens against the rulesets

| # | Attempt | Expected | Result |
|---|---|---|---|
| C1 | Job（`impl`）：`git push origin HEAD:main` | 被 ruleset 拒絕 | |
| C2 | Job（`impl`）：對一個已存在的 branch 執行 `git push --force origin redteam/c2`，然後 `git push --force origin HEAD:main` | 第一個取決於 ruleset（它們只涵蓋預設 branch）；`main` 不受影響：第二個被拒絕 | |
| C4 | Job（`impl`）：`git tag v9.9.9 && git push origin v9.9.9` | 被 `tags` ruleset 拒絕 | |
| C20 | Job（`impl`）：`git tag origin/main && git push origin refs/tags/origin/main`（名稱像預設 branch 的 tag） | 被 `tags` ruleset 拒絕。如果它竟然通過了：Mac 上的 `agentctl` 與 `risk-gate` 仍然讀取真正的預設 branch，因為它們使用完整的 ref 名稱與 base commit id | |
| C6 | Job（`review`）：對 spec pull request 執行 `gh pr review N --approve`。從 `impl` job 重複一次 | 從 `impl`：403，token 不能對 pull request 寫入。從 `review`：這次核准不算作 code owner 的核准，pull request 仍然不能被 merge | |
| C7 | Job（`impl`）與 job（`review`）：對檢查尚未通過的 pull request 執行 `gh pr merge N --squash` | 兩次都被拒絕。這只顯示紅燈的 pull request 不會被 merge。誰能 merge 綠燈的 pull request，見 C17(b) | |
| C17 | (b) 取一個進入 `main`、其他方面可以 merge 的 pull request：每個必要檢查都是綠燈，需要核准的話已核准。無害的文件變更即可。Job（`impl`）：`gh api --method PUT repos/OWNER/REPO/pulls/N/merge -f merge_method=squash`。然後以有權限的身分（admin，或 Conductor App）merge 同一個 pull request。(a) 部分在 layer 1 | agent 的嘗試被拒絕，而拒絕它的是 `main-merge` ruleset，不是 token：GitHub 的 merge endpoint 只需要 contents: write，而 `write` token 有。有權限的身分 merge 同一個 pull request 會成功，這顯示沒有其他東西擋住它。檢查為紅燈的 pull request 會被其他規則拒絕，什麼都證明不了 | |

### D. Approval, CODEOWNERS and merge rules

| # | Attempt | Expected | Result |
|---|---|---|---|
| D9 | 你核准 spec pull request 之後，再 push 另一個 commit | 你的核准失效；在你核准新的 commit 之前，pull request 不會被 merge | |
| D10 | 自己開一個變更 spec 的 pull request，然後嘗試核准它 | GitHub 不允許。這就是 pull request 必須由 Conductor App 開啟的原因 | |
| D23 | 把 draft 標為 ready。取一個仍是 draft 的 story pull request，它的 head commit 上 `security` 與 `spec-verify` 顯示為 skipped。不經 push 把它標為 ready（`gh pr ready N`，或讓 conductor 做） | 對同一個 commit 出現 `ci`、`security` 與 `spec-verify` 的全新完整執行，在它們以綠燈結束之前，pull request 不可 merge。這一項應該成功。如果在新的執行回報之前，它就依據被跳過的結果而可以 merge，那就是失敗 | |
| D24 | 手動編輯 `.github/CODEOWNERS`（加一行），並用 pull request push 該 branch。另外，在不重新產生的情況下，更改 `agentdev.toml` 中的 `[risk.t2]` | `agentctl codeowners --check`（由 layer 3 的 `ci` 執行）失敗，並指出該檔案。變更 `.github/**` 或 `agentdev.toml` 需要 code owner 的核准才能 merge | |
| D25 | 以 admin 身分，嘗試從 clone 執行 `git push origin HEAD:main`，然後透過網頁介面 merge 一個綠燈且已核准的 pull request | 直接 push 被拒絕：`main` 沒有 bypass，admin 也不例外。透過 pull request 的 merge 會成功。這一項應該部分成功 | |
| D26 | 以非 admin 的 collaborator（或不是 admin 的 token）push `v9.9.9`。以 admin 身分，建立並刪除一個暫時的 `v0.0.0-redteam` tag | 非 admin 的 push 被拒絕。admin 的 tag 被建立並刪除（這顯示 ruleset 沒有把 admin 鎖在外面）。之後刪除該 tag | |
| D27 | 從不是預設 branch 的 branch dispatch 每日 brief：`gh workflow run agentdev-brief.yml --ref SOME_BRANCH` | `brief` job 被拒絕使用 `conductor` environment，或拿到空的 `CONDUCTOR_APP_PRIVATE_KEY` 並在 App token 步驟失敗。沒有產生任何 token。如果 job 到達「Actions budget」步驟，表示 environment 的 branch 規則沒有運作 | |
| D28 | 讀取 Settings > Environments > conductor | 剛好一條 deployment 規則：預設 branch。不要為了測試而移除它 | |
| D29 | base 不是 `main` 的 pull request（例如 `story/000-example` 進入 branch `test/base`） | 必要檢查都不適用於它，`main` 的規則也不適用；它不能被 merge 進 `main`。把它改目標到 `main` 並 push：每個必要檢查就會針對 `main` 執行 | |
| D30 | Settings：嘗試從介面以 merge commit 或 rebase 的方式 merge pull request | 只提供 squash | |

## 5. Not yet verified

這一層的任何東西都還沒有在真實的 GitHub 上執行過。具體而言：

- 目前的 rulesets API 是否接受 `templates/rulesets/*.json` 中的欄位。如果它回報未知欄位，請依錯誤調整範本，並把結果寫回來。
- `main` 與 `main-merge` 是否如所述疊加（`main-merge` 中的 bypass 不會削弱 `main`），以及 Conductor App 的 ID 是否是 Integration bypass 的正確 `actor_id`。
- `main.json` 中的 `integration_id: 15368` 是否就是產生必要檢查的 GitHub Actions app，以及 reusable workflow 的檢查是否回報為 `ci / ci`、`ci / spec-verify`、`security / security` 與 `risk-gate / risk-gate`，而 `agent-review` 是單純的 commit status。
- 私有 repository 在 Team 方案上是否能使用帶有 deployment branch 規則的 environment、這些設定的確切名稱，以及如果 workflow 先指名了環境，GitHub 是否不會在沒有 branch 規則的情況下建立該 environment。
- `conductor` environment 的 secret 是否可供被呼叫的 reusable workflow 中的 job 使用。
- `review` token 的核准是否不算作 code owner 的核准。
- Conductor App 是否能對有這些 ruleset 的 repository 的 pull request 啟用 auto-merge。

## 6. Known limitations

- 私有 repository 的 ruleset 需要 Team 或更高的方案。在較低的方案上，它們不保護任何東西。
- 在套用 `agentctl rulesets 3` 之前，`main` 不要求任何檢查：只有 layer 2 時，你得到的是 pull request、code owner review 與 merge 限制，沒有 gate。
- 除了 code owner 規則之外，`main` 要求的核准 review 數為零。沒有碰到任何有 owner 的路徑的 pull request 不需要人工 review；它是 T0 或 T1，由 gate 與 conductor 的設定決定它是否自行 merge。
- Conductor App 可以透過 `main-merge` 的 bypass 更新 `main`。它的金鑰放在執行 conductor 的 Mac 上以及 `conductor` environment 中；任何能讀取其中之一的人都可以以 conductor 的身分 merge，仍然受 `main` 約束。
- repository admin 可以更改 ruleset。依設計，這裡專案上的每個人都是 admin；ruleset 防的是 agent 與意外，不是惡意的 admin。
- 如果 conductor 的 planner 提早返回，auto-merge 旗標可能仍然在不再符合條件的 pull request 上保持啟動狀態；`main` ruleset 是最後的後盾。
- 雲端 session 以某人的帳號連接（layer 1），所以它們的權限就是那個人的權限；layer 1 的 E1 到 E4 檢查那允許什麼。
