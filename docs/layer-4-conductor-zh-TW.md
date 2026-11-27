# Layer 4：Conductor

*English: [layer-4-conductor.md](layer-4-conductor.md)。兩份內容不一致時以英文版為準。*

Conductor（`agentctl conductor`）在你不在時推進工作。它是一支沒有記憶、也不使用語言模型的程式。每一輪（pass）它都從 GitHub 讀取 sprint、spec、issue、pull request 與檢查結果，算出下一步該發生的事並執行：把一個 stage 派給 agent、開啟 pull request、把 pull request 標為 ready、更新 branch、啟用或撤回 auto-merge，或把決定交給你。它在一台 Mac 的終端機中執行，身分是 Conductor GitHub App。在你把某個 tier 列入 `auto_merge_tiers` 之前，它不會自行 merge 任何東西。它不會讓 agent 變安全（layer 1）、不會保護 `main`（layer 2），也不會評判程式碼（layer 3）。這三層它都需要。請最後才採用它，並先用 shadow mode。設計與理由見 [guideline-zh-TW.md](guideline-zh-TW.md)。

這裡的內容都沒有對真實的 GitHub、Docker Sandboxes、各家廠商的雲端服務或 Mac 執行過。標示 **To verify** 的地方，是程式碼所依賴、但尚未驗證的那些服務行為。

## 1. 這一層保護什麼

Conductor 的工作是在沒有人盯著時讓工作持續前進，並在該停的時候停下來。它提供：

- **確定性的順序。** 一個 story 在它所依賴的 story 都已 merge、未被封鎖、其 `touches` 與進行中 story 的 `touches` 沒有重疊，且進行中 story 的數量未超過上限時才會開始。相同的輸入得到相同的計畫。依賴關係的規劃由 agent 完成，並由你隨 sprint 一起核准；程式只負責計算。
- **在 GitHub 允許的範圍內，不遺失、也不重複工作。** 所有記憶都在 GitHub 上（label、issue 連結、隱藏的 marker 留言）。派發會先記錄再送出，所以當機只會留下沒有 session 的 marker，並在該 stage 逾時後重試，絕不會出現沒有 marker 的 session。Marker 只有在由 conductor 自己的登入帳號，或 `[roles] humans` 中的人寫下時才會被採信。
- **保險機制（fuse）。** 一個 kill switch，以及進行中 story 數、每日 pull request 數、stage 重試次數、fix 輪數、triage session 數、未核准 spec pull request 數的上限。超過上限就升級（escalate）給你，不會無止境地重試。
- **每個 stage 的最小權限。** 每個被派發的 stage 只拿到它需要的權限：design、tests 與 impl 可以推送 branch，但不能開啟或審查 pull request；review 與 triage 可以審查，但不能推送。見 `agentctl stage-profile STAGE`。開啟 pull request 是 conductor 的工作，所以作者是 Conductor App，你可以核准它。
- **你的決定仍由你做。** T2 變更、spec 與 sprint 都等人處理。Conductor 會繞過等著你的 story，去做另一個。

它不做的事：

- 它不會把錯的 spec 變對。它只照你核准的內容建置。
- 它不評判程式碼。這是 gate 的工作，而 `agent-review` 是其中最弱的一個（[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)）。
- Mac 在睡眠或終端機關閉時它不會執行，此時沒有任何東西會前進。雲端上沒有 conductor。
- 它不支援同一個專案在不同的 Mac 上執行兩個 conductor。

## 2. 開始之前

- Layer 1、2、3 都已就位，且它們的 checklist 都已跑過：[layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)、[layer-2-github-zh-TW.md](layer-2-github-zh-TW.md)、[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)。特別是 layer-2 的 ruleset（`main`、`main-merge`、`tags`）已啟用，layer-3 的 ruleset `main-checks` 已套用（`agentctl rulesets 3`），CODEOWNERS 已產生，`ci` 在 `main` 上是綠的，且 repository 設定中的 Allow auto-merge 已開啟。
- 這台 Mac 上已安裝 kit，且 `agentctl` 可在專案內執行（[adopting-zh-TW.md](adopting-zh-TW.md)）。Launcher 會執行 default branch 上 `agentdev.toml` 所釘選的 kit 版本。
- Conductor GitHub App 已存在、已安裝在該 repository，且它的私鑰放在這台 Mac 上、專案目錄之外（layer 2）。
- `openssl` 在 path 中。它用來簽署索取 App token 的請求。
- `git` 有一個指向該 GitHub repository 的 `origin` remote，且專案是一份已 fetch default branch 的 clone。Conductor 讀的是 `origin/main`（default branch），不是你的工作目錄。
- 對你使用的每個 harness，其派發憑證（第 3.1 節）與其 cloud task 或整合（第 3.4 節）都已存在。對本機 sandbox（`via = "sbx"`），這台 Mac 已針對這個專案執行過 `agentctl sandbox setup`（layer 1）。
- Sprint 檔與它列出的 spec 已在 `main` 上，或你正要建立 spike 用的那一份（第 3.9 節）。
- 決定 conductor 為誰工作。一個 conductor 為一位 developer 執行，由 `DEVELOPER` 設定。有多人時的意義見第 3.4 節。

## 3. 設定

### 3.1 設定檔

Conductor 從 repository 之外的一個檔案讀取它的憑證：

```
~/.config/agent-dev/OWNER-REPO/conductor.env
```

若設定了 `XDG_CONFIG_HOME`，它會取代 `~/.config`。`OWNER-REPO` 是 repository 的 owner 與名稱以連字號相接。這個檔案不可放在專案目錄中：clone-mode sandbox 能讀到那裡的每個檔案，包括被忽略的檔案。建立它，並給予機密檔案的權限：

```bash
mkdir -p ~/.config/agent-dev/OWNER-REPO
```

```bash
touch ~/.config/agent-dev/OWNER-REPO/conductor.env && chmod 600 ~/.config/agent-dev/OWNER-REPO/conductor.env
```

檔案內容是 `KEY=VALUE` 行；空白行與以 `#` 開頭的行會被忽略，值外面的一層引號會被去掉：

```ini
# The Conductor App. The key path must be absolute; "~" is not expanded.
CONDUCTOR_APP_ID=123456
CONDUCTOR_APP_KEY=/Users/YOU/.config/agent-dev/OWNER-REPO/conductor-app.pem
# Your GitHub login. This conductor does not dispatch a story that the sprint gives to someone else.
DEVELOPER=DIRECTOR_LOGIN
# Dispatch credentials, for the harnesses you use. Plain names: on your Mac they are yours.
CLAUDE_TRIGGER_URL=https://...
CLAUDE_TRIGGER_TOKEN=...
DISPATCH_TOKEN=...
```

`CONDUCTOR_APP_ID`、`CONDUCTOR_APP_KEY` 與 `DEVELOPER` 為必填。缺少時 `agentctl conductor` 會停止，並顯示一則指出檔案與缺少的 key 的訊息。派發憑證只有你的 role 所用的 harness 才需要：

| Name | 用於 | 來源 |
|---|---|---|
| `CLAUDE_TRIGGER_URL`, `CLAUDE_TRIGGER_TOKEN` | `via = "http"` 的 harness（Claude Code on the web）：cloud scheduled task 的 API trigger | 該 scheduled task 的 API trigger（[layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)，cloud agents） |
| `DISPATCH_TOKEN` | `via = "comment"` 的 harness（例如 Codex cloud）：一個 GitHub token，其帳號是與該 cloud task 連結的那個帳號，用來張貼 mention | 該帳號的 fine-grained personal access token，對這個 repository 有 issues 與 pull requests 的寫入權限 |

變數名稱來自 `agentdev.toml` 中該 harness 的 `url_env` 與 `token_env`；想用別的名稱就在那裡修改。`via = "sbx"` 的 harness 在這裡不需要憑證：它的 sandbox 會從你的 agent App 取得 token（[layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)）。

Conductor 在 GitHub 上以 Conductor App 的身分行動，不是以你的身分。它每一輪都用金鑰自行產生 App 的 token。若它以你的身分行動，你就會是它所開啟的 pull request 的作者，而 GitHub 不允許作者核准自己的 pull request。

一個 story 使用哪些憑證：sprint 指派給 `default` 的 story，用純名稱。指派給登入帳號為 `DEVELOPER` 的 developer 的 story，先用加後綴的名稱（`DISPATCH_TOKEN_ALICE`，登入帳號轉大寫，其他每個字元換成 `_`），再用純名稱。指派給其他人的 story 完全不會從這台 Mac 派發（第 3.4 節）。

Claude review 不使用這些憑證派發。它以 workflow job 的形式在 GitHub 上執行，使用 `conductor` environment 的 secret（[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)，第 3.7 節）。

### 3.2 Conductor 讀取的 repository 變數

在 repository 的 Settings > Secrets and variables > Actions > Variables 設定（或用 `gh variable set`）。它們不含任何機密。

| Variable | 意義 | 何時需要 |
|---|---|---|
| `CONDUCTOR_PAUSED` | `true` 會暫停 conductor（第 3.8 節）。未設定或為 `false` 則讓它執行 | Kill switch。請先建立為 `false`，以確認 App 能讀取它（checklist F14） |
| `CONDUCTOR_QUOTA` | JSON，例如 `{"default/codex": 1795800000}`：該 harness 的額度恢復的 epoch 秒數。Key 是 `<developer>/<harness>`，`default` 的 story 用 `default` | 手動把某個 harness 標為額度用盡。Conductor 隨後會改用清單中的下一個 harness |
| `CONDUCTOR_BOT` | 通常不設定。Conductor 會從 App 自行算出它的登入帳號（`APP-SLUG[bot]`）。在這裡設定的登入帳號，也會被採信為 marker 留言的作者 | 只在以其他登入帳號寫下的 marker 仍必須被採信時才用。被列在這裡的人能左右 conductor |
| `REVIEW_BOTS` | 其 pull request review 算作 agent review 的登入帳號 | 見 [layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md) |

### 3.3 執行

在專案內執行，任何 branch 都可以：

```bash
agentctl conductor
```

它會印出 `conductor is running here as APP-SLUG[bot], every 180s. Ctrl-C stops it.`，然後每 180 秒執行一輪（`--interval SECONDS` 可以更改）。按 Ctrl-C 停止；它會印出在它再次執行之前沒有任何東西會前進。請把它留在一個持續開著的終端機中（Mac 上的 terminal multiplexer 可以做到）。

關於它從哪裡讀取，它保證：

- 每一輪它都會 fetch default branch，並從 `origin/<default branch>` 的一個 detached worktree 讀取使用中的 sprint、spec、roadmap 與 `agentdev.toml`；這個 worktree 放在 repository 的 git 目錄內（`agentctl-main`）。它絕不從你的工作樹讀取，所以你 checkout 了什麼、或某個 agent 的 branch 是什麼，都不能改變它的行為。執行的程式碼是所釘選版本的已安裝 kit。
- 它啟動的 sandbox 從你的專案目錄（`AGENT_PROJECT_DIR`）clone repository。

一個 lock 檔（`conductor.lock`，在 `~/.local/state/agent-dev/OWNER-REPO/`）使同一台 Mac 上同一專案的第二個 conductor 無法啟動；它會以「another conductor for this project is already running on this Mac」停止。Lock 在程序結束時釋放，無論它如何結束。另一台 Mac 上的 conductor 不受支援，也沒有任何機制阻止它。（Known limitation。）

當某一輪失敗（例如網路中斷），它會印出 `pass failed: ...`，下一輪照排程執行。連續三輪失敗後，它在每輪之間等 15 分鐘，直到有一輪成功，並印出它這麼做了。

Mac 睡眠或闔上螢幕時，沒有任何東西會前進，也沒有任何東西遺失：喚醒後，下一輪會重新讀取狀況。已在雲端執行的 session 會繼續。

### 3.4 Dry run

想看它會做什麼、但不實際做任何事：

```bash
agentctl conductor --dry-run
```

它執行一輪、在每個動作前加上 `DRY-RUN` 印出計畫，然後結束。它不取得 lock，所以可以在 conductor 執行時同時執行，而且它不會在 GitHub 上建立任何東西：沒有 issue、label、留言、pull request 或變數。它仍會產生 App 的 token，並更新 `origin/main` 的本機 worktree。暫停時它只印出 `halt`，因為暫停中的 conductor 不計算計畫。

計畫這樣讀：`dispatch story=012 stage=design harness=claude attempt=1` 是一個將要開始的 stage；`open-pr` 是一個已推送、將要得到 pull request 的 branch；`enable-auto-merge`、`disable-auto-merge`、`mark-ready`、`update-branch` 就是字面上的意思；`notify` 與 `escalate` 是給你的訊息；`halt` 是暫停。

### 3.5 Role 與 harness 路由

誰做什麼，全都在 `agentdev.toml` 中，疊加在 kit 的預設值（`tools/agentctl/defaults.toml`）之上。List 會整個取代預設值；table 則逐個 key 合併。更改 `agentdev.toml` 屬於 T2。

**Harness。** Harness 說明一個 stage 如何啟動。每一個都是 table `[roles.harness.NAME]`，帶有 `via`：

| `via` | 作用 | 需要 |
|---|---|---|
| `http` | 把 prompt POST 到 cloud scheduled task（Claude Code on the web）的 API trigger | `conductor.env` 中的 `url_env`、`token_env`。URL 必須以 `https://` 開頭 |
| `comment` | 以 token 背後的帳號，把 `<mention> <prompt>` 作為留言張貼在該 story 的 pull request 上，若尚無 pull request 則貼在它的 issue 上（Codex cloud 讀取 `@codex`） | `conductor.env` 中的 `token_env`；`mention` |
| `sbx` | 為該 stage 在這台 Mac 上啟動一個全新的 clone-mode Docker Sandbox，結束後移除它（`agentctl sandbox job ...`）。用於 Ollama，也作為無法運作的雲端路徑的 fallback | 這台 Mac 已完成 `agentctl sandbox setup`。只在 conductor 於這台 Mac 上執行時才會執行 |
| `review_workflow`（設在 harness 上） | Review stage 以 workflow job 的形式執行，由該 job 自行設定 `agent-review` status。`claude` 的預設值是 `agentdev-agent-review.yml` | `conductor` environment 的 secret `CLAUDE_CODE_OAUTH_TOKEN`（[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)） |

預設值定義了 `claude`（`http`，帶 `review_workflow`）、`codex`（`comment`，`@codex`）與 `ollama`（`sbx`）。Conductor 在每次派發中都送出完整渲染後的 stage prompt；prompt 屬於 kit（`prompts/*.md`，由 `agentdev.toml` 填入）。要看其中一個：

```bash
agentctl prompt impl
```

**每位 developer 的 stage。** 對每個 stage，harness 依序嘗試；使用第一個有額度的。`default` 涵蓋沒有 assignee 的 story，以及所有沒被列出的人：

```toml
[roles.developers.default.stages]
design = ["claude"]
tests = ["claude"]
impl = ["claude", "codex"]
review = ["codex", "claude"]
triage = ["claude"]
```

Fix 輪與 conflict 解決使用 `impl` 清單。對 `review`，當 developer 有選擇時，conductor 會把與實作該 story 者不同的 harness 排在前面，讓審查者與實作者不同。

| 設定 | 審查者 | 你放棄的東西 |
|---|---|---|
| 一個人、一家廠商 | 同一個 harness 的全新 session | 跨廠商的審查。主要的保證由機械式檢查提供 |
| 一個人、多家廠商 | 與實作者不同的廠商 | 只要兩邊額度都夠，就沒有 |
| 多個人，各有自己的 AI | 各人自己的組合所允許的任何一種 | 只有一家廠商的人，其 story 會得到同廠商的審查 |

如果你只用 Codex，請在每個 stage 都列 `codex`，設定 `planner = "codex"`，並讓你的 review 經由 bridge（`REVIEW_BOTS`）來自 Codex 整合。如果你只用 Claude，預設值只需要把 `impl` 與 `review` 清單改成只有 `claude`。

**人員。** `[roles] directors` 核准 spec 與 sprint，並擁有 CODEOWNERS 中的 guardrail。`humans` 是所有其核准對 T2 變更有效的人；directors 包含在內。`planner` 是在沒有暗示特定 developer 時，起草 spec 與 sprint 的 harness。`agentctl init DIRECTOR [HUMAN ...]` 會填入前兩者。

**這是誰的 story。** 這來自 sprint 檔，絕不來自 issue 的 assignee：`assignee` 是該 sprint 的預設值，`[owners]` table 為個別 story 指定另一位 developer。Conductor 派發指派給它自己的 `DEVELOPER` 的 story，以及 `default` 的 story。指派給其他人的 story 會被延後（deferred），不論它的 harness 以哪種路徑啟動：不寫入任何東西，計畫會印出 `deferred`。它由那個人 Mac 上的 conductor 派發，該 conductor 的 `DEVELOPER` 設為他們的登入帳號。因此他們 `via = "sbx"` 的 stage 只有在他們的 conductor 執行時才會前進。對你的 story，另一個人的 conductor 也會做所有不屬於派發的事（開啟 pull request、標為 ready、更新 branch），所以那裡沒有空檔，但同一專案有兩個 conductor 正是不被支援的。有多於一位 developer 時，開始前先決定誰執行 conductor，並把 sprint 的 story 指派給 `default` 或那個人。（Known limitation。）

### 3.6 Sprint 與 spec

Conductor 從 default branch 讀取這些，路徑由 `[paths]` 設定（以下為預設值）：

| 內容 | 位置 | 備註 |
|---|---|---|
| Roadmap | `docs/product/roadmap.md` | 每行一項需求，格式為 `- [ ] text`（未勾選：還沒有 spec）或 `- [x] text`（spec 已存在）。只要有未勾選的行，且未核准的 spec pull request 少於 `max_open_spec_prs`，conductor 就會派發 product-owner stage，為第一個未勾選的行起草一份 spec |
| Sprint | `docs/sprints/NNN.toml` | 編號最大的檔案是使用中的 sprint。Key：`goal`、`length_days`、`stories`（id 清單）、`assignee`（預設 `"default"`）、選用的 `[owners]`（`"012" = "alice"`）。Sprint 000 是 `agentctl init` 建立的空佔位檔；它不派發任何東西 |
| Story | `docs/specs/NNN-slug/` | `story.md` 與 `story-<lang>.md`（你用來核准的語言），以及 `spec.toml`，內含 `priority`、`size`、`risk`、`depends_on`、`touches`、AC、TC 與 `done_when`。kit 中的 `examples/specs/000-example/` 是一個完整範例 |

`depends_on`（必須先 merge 的 story）與 `touches`（該 story 所變更的模組與共用資源，例如 `db:orders`）由 planner 撰寫，並由你隨 sprint 一起核准。依賴不在 sprint 內的 story、或有循環依賴，會使該 sprint 停止並升級一次。`touches` 是一種預測，一定會有遺漏；代價是 merge conflict，conductor 會把它交給 agent 解決。

Story id 的長度為 `[stories] id_digits`（預設 3）。對使用中 sprint 的每個 story，conductor 會（一次）建立一個標有 `story:NNN` 的追蹤 issue，以及一個標有 `sprint:NNN` 的 sprint issue；這些 issue 存放它的 marker 與通知。Story 的 branch 必須正好是 `story/NNN-slug`，slug 來自它的 spec；`story/NNN-other` 這樣的 branch 會被忽略。

### 3.7 Stage 流程

對每個 story，一次一個 stage。每個 stage 都是沒有記憶的新 agent session；它需要的一切都在 spec、issue、branch 與歷史中。

| 順序 | Stage | 發生什麼 | 回報方式 |
|---|---|---|---|
| 1 | `design` | Design agent 撰寫設計文件並推送 `story/NNN-slug` | Agent 在 story issue 上加上 label `done:design` |
| 2 | `tests` | Test agent 只依據 story 撰寫測試；此時它們必須失敗 | `done:tests` |
| 3 | `impl` | Implementation agent 讓測試通過 | `done:impl` |
| 4 | mark ready | Conductor 在 branch 首次推送時以 draft 開啟 pull request。`done:impl` 之後它把 pull request 標為 ready，完整的 gate 第一次執行 | |
| 5 | `review` | 機械式檢查都是綠的時候，review 針對 head commit 派發，並設定 `agent-review` | Commit 上的 status；workflow 路徑則是 `done:review` |
| 6 | merge | 在 shadow mode：由你 merge。在 `auto_merge_tiers` 之後：conductor 啟用 auto-merge。接著 `evidence` 把表格貼到該 story 的 issue 上 | |

其他 stage：`fix`（檢查失敗，或 review 要求修改；最多 `max_fix_rounds` 次）、`resolve-conflict`（branch 與 main 衝突）、`triage`（某個 stage 失敗或反覆停滯）、`fix-main`（main 是紅的；一個修復任務，在 main 變綠之前不派發其他任何東西）、`product-owner`（依 roadmap 起草 spec）、`planner`（起草下一個 sprint，在 `draft_next_sprint_at` 比例的 story 已 merge 時）。

與 commit 的綁定：fix、conflict 解決與 review 都綁定於它們被派發時的那個 commit。在 branch 移動之前，fix 都算進行中。每個新 commit 都需要自己的 review 結論。當 branch 落後 main 時，conductor 會更新它。

Pull request：對任何已推送、位於 `story/`、`spec/`、`sprint/` 或 `chore/` 之下且沒有指向 default branch 的 pull request 的 branch，conductor 會為它開啟一個。Story 得到 draft；其他的則得到可供審查（ready for review）的 pull request。它每天最多開啟 `max_prs_per_day` 個 story pull request（以 UTC 日期計算）。

**Spec 與 sprint pull request** 是你的決定。以 code owner 的身分核准其中一個，在下一輪 conductor 就會對它啟用 auto-merge，並在檢查為綠時 merge。這不取決於 `auto_merge_tiers`。不需要任何人審查的 pull request 沒有 review decision，絕不會被這樣處理。`chore/` pull request 絕不會被 conductor merge：由你 merge。

等你處理的情況：一個 story，其 pull request 是 T2 且其他一切皆綠、有被要求的 review、或帶有 label `needs-human` 或 `blocked`，會等人處理。它不佔進行中 story 的名額，但仍保有對它 `touches` 的占用。Conductor 會繞過它。當每個未完成的 story 都在等人時，它會停止並通知你一次。Sprint 完成時，它會通知你，開發停止，直到下一個 sprint 獲得核准；只有 spec 的起草會繼續。

### 3.8 Fuse、kill switch 與升級

預設值在 `defaults.toml` 的 `[conductor]` 中：

| 設定 | 預設值 | 意義 |
|---|---|---|
| `wip_limit` | 2 | 同時進行中的 story 數。等人處理的 story 不佔名額 |
| `max_prs_per_day` | 10 | 每天開啟的 story pull request 數 |
| `max_attempts` | 2 | 在要求 triage session 之前，同一個 stage 的派發次數 |
| `max_fix_rounds` | 3 | 在詢問人之前的 fix、review 循環次數 |
| `max_triage` | 1 | 在詢問人之前，每個 story 的 triage session 數 |
| `max_open_spec_prs` | 3 | product-owner stage 可以留著等待的未核准 spec pull request 數 |
| `draft_next_sprint_at` | 0.8 | 當 sprint 已 merge 的比例達到此值時，起草下一個 sprint |
| `stage_timeout_minutes` | default 90、design 45、review 45、triage 30、product-owner 60 | 被派發的 stage 在被視為停滯之前可以執行多久 |
| `max_parked_hours` | 72 | 因 triage 新增的依賴而被擱置（parked）的 story，在超過這個時間都沒有任何進展時會被升級 |
| `max_dispatches_per_story` | 15 | 各 stage 合計的 session 數，從該 story 上次升級後起算。會超過此數才要啟動 session 的 story 會被升級；其最後一個 session 已完成它的則不會 |
| `remind_after_hours` | 48 | 等人處理的 story（`needs-human`、`blocked`、T2 或 review 核准）會在 sprint issue 上再被提及一次，每次等待一次。這個提醒不會抑制「sprint stalled」通知 |
| `auto_merge_tiers` | `[]` | Conductor 可以 merge 的 tier（第 3.10 節） |

**停滯與失敗的 stage。** 一個 stage 在逾時之後仍未回報，就會再次派發（attempt 2）。達到 `max_attempts` 後，會派發一個 triage session。Triage agent 只能新增一個「blocked by」連結、附上說明要求重試，或附上選項後升級；它不能更改 spec、sprint、程式碼或測試。達到 `max_triage` 後，該 story 就會被升級。

**升級（Escalation）。** Conductor 在 story issue 上加上 label `needs-human`，並留言 mention `[roles] humans` 中的每個登入帳號。它不會把 issue 指派給任何人。從此它會繞過該 story。要恢復：閱讀 issue 上的說明與選項、做決定、移除 label，如果 spec 需要修改，就透過一般的 spec pull request 修改。加上 `blocked` 可以刻意不去動某個 story。升級會發生在：一個 stage 在重試與 triage 之後仍失敗；檢查或 review 在 `max_fix_rounds` 之後仍失敗；stage 已回報完成但沒有 branch 或 pull request；sprint 計畫有問題（缺少依賴或循環）；一個 story 被擱置超過 `max_parked_hours`；一個 story 用掉了 `max_dispatches_per_story` 個 session。升級會點名等待被升級者的 story（"Waiting for it: 002."）。這些 story 本身不會被升級；解決那一個就會釋放它們。當被擱置的 story 回來時，session 仍在執行的那一個會先被接納並保有它 touches 的東西，所以回來的 story 絕不會與它並行啟動。

**Kill switch。** 把 repository 變數 `CONDUCTOR_PAUSED` 設為 `true`：

```bash
gh variable set CONDUCTOR_PAUSED --body true
```

每一輪都會即時讀取它。暫停時 conductor 不派發任何東西、也不開啟任何 pull request。它只做一件事：把每個已開啟 auto-merge 的 open pull request 的 auto-merge 關掉，因為否則 GitHub 會在這種 pull request 的檢查轉綠時自行 merge 它。這發生在下一輪執行時，而不是你設定變數的那一刻，所以要立即停止的話，對每個這樣的 pull request 還要執行：

```bash
gh pr merge NUMBER --disable-auto
```

已在執行的 session 不會被停止。要恢復：

```bash
gh variable set CONDUCTOR_PAUSED --body false
```

`CONDUCTOR_PAUSED`、`CONDUCTOR_BOT` 與 `CONDUCTOR_QUOTA` 會最先、且一起被讀取。讀不到的變數不會被當作未設定：該輪的行為如同已暫停（它會印出 "treated as paused: cannot read the repository variable ..."）。派發會立即停止；已開啟的 auto-merge，只有在能列出 pull request 並成功呼叫 GitHub 的那一輪才會被撤回。如果 GitHub 的 API 整個失效，`gh pr merge NUMBER --disable-auto` 是 fallback。（**To verify**：以 Conductor App 身分使用 `--disable-auto`。）

### 3.9 Spike：先證明一個完整的循環

在處理真正的 story 之前，用一個玩具 story 在 shadow mode 下驗證整條路徑。Spike 就是 sprint 001。目標是看到以下的順序，且除了所示的指令之外不需要任何手動指令。請在一個人的設定都完成的情況下進行，一次一條雲端路徑；如果兩者都用，請讓 Claude 與 Codex 各做一次實作。

沒有人手動開啟 pull request：branch 被推送，由 conductor 以 Conductor App 的身分開啟 pull request。你自己開啟的 pull request，你是無法核准的。

1. 在 conductor 沒有執行的情況下，依 `agentctl init` 複製的範本，在 branch `sprint/001` 上建立 spike 的 spec 與 sprint：

```bash
git switch -c sprint/001
```

```bash
cp -R docs/specs/_template docs/specs/001-hello
```

```bash
cp docs/sprints/_template.toml docs/sprints/001.toml
```

   填寫三個 spec 檔（一個小功能，含一個 AC 與兩個 TC）與 sprint 檔（`stories = ["001"]`）。如果 `conductor.env` 中的憑證用的是純名稱，就把 `assignee` 留為 `default`。只有在你也使用加後綴的名稱時才用你的登入帳號。指派給具名者的 story 會先使用該人加後綴的名稱，只有在那個人自己的 Mac 上才會退回使用純名稱。

   玩具功能請用專案本身的語言，並確認 `agentdev.toml` 的 `[tests]` 會執行它並寫出 JUnit XML（[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)，第 3.3 節）。測試的名稱要帶有它的 TC id，例如 `test_tc_001_01_says_hello`。然後檢查、commit 並推送：

```bash
git add docs/specs/001-hello docs/sprints/001.toml && git commit -m "Add the spike story and sprint 001" && git push -u origin sprint/001
```

2. 先暫停，讓 sprint 檔的 merge 不會啟動真正的執行，然後啟動 conductor：

```bash
gh variable set CONDUCTOR_PAUSED --body true
```

```bash
agentctl conductor
```

   讓它持續執行。暫停時它只印出 `halt`。

3. 解除暫停，等 conductor 為 `sprint/001` 開啟 pull request（ready for review）：暫停時它不開啟任何東西。然後在你核准之前再暫停。

```bash
gh variable set CONDUCTOR_PAUSED --body false
```

   等到 `ci`、`security`、`spec-verify` 與 `agent-review` 都是綠的。此時 `risk-gate` 是紅的，這是正確的：spec 與 sprint 檔屬於 T2，`risk-gate` 只有在 `[roles] humans` 中的某個人核准目前的 commit 後才會通過。

4. 暫停、核准該 pull request，並這一次自己 merge 它，讓下一步從已知的狀態開始：

```bash
gh variable set CONDUCTOR_PAUSED --body true
```

```bash
gh pr merge sprint/001 --squash
```

5. 在暫停時要求一份計畫。它只會印出 `halt (kill switch is on)`。這證實 kill switch 有效：

```bash
agentctl conductor --dry-run
```

6. 解除暫停並立刻要求一份計畫：

```bash
gh variable set CONDUCTOR_PAUSED --body false
```

```bash
agentctl conductor --dry-run
```

   它應該列出對 story 001 派發 `design`，沒有其他出人意料的東西。執行中的 conductor 會在三分鐘內自己執行一輪，所以實際的執行可能先發生；這裡無妨。
7. Conductor 派發 `design`。Agent 推送 `story/001-hello`，conductor 以 draft 開啟 pull request。在 draft 上，`ci` 只執行 lint，`risk-gate` 會執行，`security` 與 `spec-verify` 會被跳過。
8. `done:design`、`done:tests` 與 `done:impl` 依序出現。`done:impl` 之後 conductor 把 pull request 標為 ready，完整的 gate 第一次執行。
9. `agent-review` 針對 head commit 派發，並把 status 寫在該 commit 上。沒有完成的 review 會以 failure 發布，絕不會被留成通過。
10. 五個檢查都是綠的，且 head commit 也帶有 status `risk-tier/T1`（或 `T0`）。在 shadow mode 下，conductor 在 sprint issue 上留言說明該 pull request 可以 merge；由你按下 merge。
11. `evidence` 把可追溯性表格貼到 story issue 上。

如果任何一步卡住，請記下卡在哪裡以及錯誤訊息：

| 卡住的地方 | 怎麼做 |
|---|---|
| Conductor 在啟動時以 "must define ..." 停止 | `conductor.env` 不存在，或缺少 `CONDUCTOR_APP_ID`、`CONDUCTOR_APP_KEY` 或 `DEVELOPER`。訊息會指出該檔案 |
| 某一輪在讀取狀態時失敗 | 看 `pass failed:` 那一行。讀取的程式碼（`tools/agentctl/github.py` 中的 `collect`）還沒有對真實的 API 執行過。請在 kit 中修正並把結果寫回 |
| 它拿不到 token | 金鑰路徑不是絕對路徑、App 沒有安裝在該 repository，或缺少 `openssl` |
| Branch 已推送但沒有 pull request 出現 | Conductor 已暫停或未執行、branch 名稱不是以 `story/`、`spec/`、`sprint/` 或 `chore/` 開頭、`story/` branch 不是 spec 所給的確切名稱，或已達到 `max_prs_per_day`。等一個間隔 |
| Pull request 已開啟但檢查沒有執行 | 它必須由 Conductor App 開啟，不能用 `GITHUB_TOKEN`。檢查只對指向 default branch 的 pull request 執行 |
| 已核准的 spec 或 sprint pull request 沒有 merge | Conductor 在核准之後的下一輪才會啟用 auto-merge。確認它在執行且未暫停、Allow auto-merge 已開啟、核准來自 code owner，且你核准的那個 commit 上五個檢查都是綠的。核准之後的任何 push 都會使核准失效 |
| 無法從雲端觸發某個 harness | 在 `agentdev.toml` 中把它改成 `via = "sbx"`（在 `chore/` branch 上的 T2 變更）。它的 stage 之後會在 conductor 執行期間，於這台 Mac 的 Docker Sandbox 中執行 |
| 計畫顯示 `deferred` | 該 story 被指派給另一位 developer。把它指派給 `default` 或你的登入帳號，或在那位 developer 的 Mac 上執行 conductor |
| 派發失敗並顯示 "no dispatch token configured" 或 "no https trigger URL configured" | `conductor.env` 中缺少該 harness 與 developer 的憑證 |
| Agent 沒有加上 `done:*` label | Agent 身分需要 issue 的寫入權限。必要時加強 prompt |
| `agent-review` 一直是 pending | 見 [layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md) 第 3.7 節：review 沒完成時，workflow 的 `publish` job 會設為 failure，所以 pending 表示執行從未開始、無法解析 pull request，或因為 branch 已移動而停止。對於 bot 或 sandbox review，檢查 `REVIEW_BOTS` |
| `spec-verify` 在 "Keep only plain result files" 失敗 | 結果中含有 symbolic link。看看測試步驟在 `reports/` 下寫了什麼 |
| Red-green 以 "its test did not run on base" 失敗 | Story 的測試檔在 base branch 上沒有被抓到。檢查 `test_paths`，以及 TC id 是否在測試名稱中 |
| 即使 tier 在 `auto_merge_tiers` 中，conductor 仍從不對一個全綠的 story pull request 啟用 auto-merge | 它從 commit status `risk-tier/T?` 讀取 tier。檢查該 status 是否在 head commit 上 |

也請記錄 [layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md) 要求的數字（每次測試執行的分鐘數、每個 story 的完整 gate 執行次數、每個 story 的 Actions 分鐘數）。

之後的第一個真正的 sprint 是 sprint 002。在 roadmap 中加幾行並 merge，或在與 product-owner agent 的聊天中討論。Product-owner stage 會為每個 story 推送一個 `spec/` branch，並由 conductor 開啟 pull request。核准它。當目前的 sprint 接近完成時，planner 會起草下一個 sprint；第一個真正的 sprint 則請手動要求（依循 `planner` prompt 的一個 session，`agentctl prompt planner`）。核准 sprint pull request，之後就由 conductor 接手。

### 3.10 分階段開啟 auto-merge

`auto_merge_tiers = []` 是 shadow mode，也是預設值。每個 gate 都會計算並回報，但由你按下 merge；conductor 只在 sprint issue 上留言說某個 story「可以 merge」。新專案的測試還不夠好，不足以作為 merge 的依據。

至少在 shadow mode 待滿一個 sprint。每次 conductor 說某個 pull request 可以 merge，花一分鐘做出你自己的判斷，並記下你是否同意。當你一直都同意時，在 `chore/` branch 上更改 `agentdev.toml`：

```toml
[conductor]
auto_merge_tiers = ["T0"]
```

再過一段時間之後，加入 `"T1"`。這個變更是 T2，需要你的核准。T2 絕不會被接受放在這個清單中。Auto-merge 的可信度受測試品質的上限所限制，這就是要分階段進行的原因。

運作方式：當一個 story pull request 的所有 gate 都已通過，且它的 tier（`risk-tier/*` commit status，不是 label）在清單中時，conductor 會針對那個確切的 commit 啟用 auto-merge（`--match-head-commit`）。如果 branch 已移動，GitHub 會拒絕，由下一輪重新判斷。GitHub 會在之後的 push 之間保留 auto-merge 請求，所以每一輪 conductor 都會從不再符合資格的 pull request 撤回它（draft、尚有 human review 未完成、檢查或 `agent-review` 不是綠的，或 tier 不在清單中），並在它符合資格時再次啟用。當 main 是紅的、sprint 計畫有問題（缺少依賴或循環）、以及使用中 sprint 的 story 都不為某個已啟動 auto-merge 的 story pull request 背書時，它也會從每個 story pull request 撤回。它依據的 tier 是 `risk-tier/*` status，其說明寫著該 pull request「pull request #N into BRANCH」並指向 default branch；為其他 pull request 或 base 計算的 status 不被採信。從 push 到下一輪之間，請求仍處於啟動狀態。GitHub 本身仍然要求新 commit 上的五個檢查都通過，且 `risk-gate` 會讓 T2 commit 失敗，直到有人核准。這個空窗期可能放行的，是 tier 高於已啟用的 tier、但低於 T2 的 commit（只啟用 T0 時的 T1），且它在 conductor 下一輪之前也通過了 `ci`、`spec-verify` 與 `agent-review`。（**To verify**：GitHub 是否會在 push 之間保留該請求；見 D22。）

### 3.11 新增一個人

1. 他們加入 organization 並成為 repository admin（[layer-2-github-zh-TW.md](layer-2-github-zh-TW.md)）。
2. 在 `agentdev.toml` 中，把他們的登入帳號加到 `[roles] humans`，並給他們一個 `[roles.developers.LOGIN.stages]` table。重新產生 CODEOWNERS（`agentctl codeowners > .github/CODEOWNERS`），並在同一個 pull request 中 commit 兩者。只有在他們要核准產品決策時才把他們加入 `directors`：只有 directors 擁有 `docs/specs/`、`docs/sprints/` 與 `docs/product/`。這是 T2 變更。
3. 他們依循 [layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)：自己的 agent App、自己的 sandbox、自己的雲端帳號。他們的 review token 放在 `conductor` environment 中，名稱為 `CLAUDE_CODE_OAUTH_TOKEN_<LOGIN>`；他們的派發憑證放在他們自己 Mac 上的 `conductor.env`，`DEVELOPER` 設為他們的登入帳號。
4. 對屬於他們的 story，在 sprint 檔的 `[owners]` table 中指名他們，或讓他們成為該 sprint 的 `assignee`。在 issue 上設定 assignee 沒有作用。
5. 決定誰執行 conductor（第 3.5 節）。整個專案只能有一個 conductor 在執行。

### 3.12 日常運作

你做四件事：在 roadmap 加一行，或對 product-owner agent 說一句話；核准或回答 spec pull request；核准 sprint pull request；推送 release tag。你看兩個地方：Director's brief（一個固定的 issue，每天更新，週一有每週稽核的段落：各 tier 的 merge 數、revert、升級，以及一份隨機抽樣、未經人工而 merge 的 pull request，供你抽查），以及你的 GitHub 通知（需要你審查的 pull request 與提到你的 issue）。

| 情況 | 怎麼做 |
|---|---|
| 你想暫停一切 | 把 `CONDUCTOR_PAUSED` 設為 `true`（第 3.8 節） |
| 你想知道目前的狀態 | Director's brief issue，或 `agentctl status --markdown` |
| 你想知道 conductor 接下來會做什麼 | `agentctl conductor --dry-run` |
| 一個 story 被標上 `needs-human` | 閱讀 issue 上的 triage 說明與選項、做決定、移除 label。如果 spec 需要修改，就修改 spec |
| 某個 harness 的額度用盡 | 設定 `CONDUCTOR_QUOTA`（第 3.2 節）。到期後 conductor 會再次使用該 harness |
| 你想暫時不動某個 story | 在它的 issue 上加上 `blocked` label |
| 你想發布 release | 在你要放在 `main` 上的那個 commit 上放一個 `v*` tag 並推送。除非 `ci / ci`、`security / security` 與 `ci / spec-verify` 各自都存在於該 commit 上且是綠的，否則 release template 會失敗 |
| 你想知道 Actions 用了多少 | `agentctl budget --dry-run`，或 brief 的第一行。這是估計值 |
| Actions 額度快用完了 | 見 [layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md) 第 3.8 節。超額用量是關閉的；CI 會停到下個月，或直到你付費購買更多 |
| 一個 story 應該使用某個人的訂閱 | 在 sprint 檔中指名他們（`assignee`、`[owners]`） |
| 一個 review stage 必須在本機 sandbox 中執行 | 給該 harness `via = "sbx"` 且不設 `review_workflow`，並把審查的 developer 的 agent App 登入帳號加到 `REVIEW_BOTS` |
| 一個 `chore/` pull request 準備好了 | 自己 merge 它。Conductor 絕不 merge 它 |
| 你需要更改 pipeline 本身 | 直接在 session 中要求 agent；工作在 `chore/` branch 上進行，並由你核准 pull request |
| 你闔上了筆電 | 沒有任何東西會前進。喚醒後下一輪會接著做。沒有交接給雲端 |
| 你懷疑哪裡出了問題 | 暫停，然後跑完四層的 checklist |

## 4. Checklist

在設定完成時執行一次，之後每次更改 `agentdev.toml`、kit 版本或 conductor 的憑證時再執行。**大多數項目都是嘗試做一件必須失敗或被拒絕的事。** 如果這樣的嘗試成功了，表示有一道防線沒有發揮作用。少數項目檢查正常路徑是否可行，預期成功：D16、F2 與 F17。D22 有一部分預期成功。「Expected」欄會說明是哪一種。

請在「Result」欄記下你實際看到的訊息。這些項目都沒有對真實的 GitHub 執行過，所以不同的結果也可能表示這份 checklist 有誤。這也請寫回。項目 id 與其他 layer 文件共用，且絕不重複使用。F5、F8（lease 與 Actions conductor）已不存在；它們的 id 保持作廢。F6、F10 與 F17 已因 lock 檔與單一本機 conductor 而改寫。

### D. 涉及 conductor 的 gate

項目 D1 至 D8、D11 至 D15、D17 至 D19 與 D21 在 [layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)；D9、D10 與 D23 在 [layer-2-github-zh-TW.md](layer-2-github-zh-TW.md)。

| # | Attempt | Expected | Result |
|---|---|---|---|
| D16 | 推送一個 branch `spec/NNN-slug`，內含一份新 spec，然後等待。接著核准該 PR，不做其他任何事 | Conductor 開啟 PR，為 ready for review，且沒有 auto-merge。在你核准之後，conductor 的下一輪啟用 auto-merge，且檢查為綠時 PR 會 merge。這一項應該成功（SUCCEED）。在你核准之前，auto-merge 不得啟用，也不得 merge | |
| D20 | Tier label。只把 `T0` 放進 `auto_merge_tiers`（`agentdev.toml`，在 main 上）。取一個 T1、所有檢查皆綠的 story PR。用 agent 的 token，把它的 label 從 `tier:T1` 改為 `tier:T0`：`gh api repos/OWNER/REPO/issues/N/labels -f "labels[]=tier:T0"`，然後 `gh api --method DELETE repos/OWNER/REPO/issues/N/labels/tier:T1`。執行 `agentctl conductor --dry-run` | Conductor 不會為該 PR 規劃 `enable-auto-merge`。它從 head commit 上的 commit status 讀取 `risk-tier/T1`，而不是從 label，並回報 merge 留給人處理。Auto-merge 維持關閉 | |
| D22 | 跨 push 的 auto-merge。把 `T1` 放進 `auto_merge_tiers`，或用一個啟用了 `T0` 的 T0 變更。等到 conductor 已對一個 head 符合資格、但尚未 merge 的 story PR 啟用 auto-merge（讓一個必要檢查保持未完成，例如讓 branch 落後 `main`）。然後以 agent App 的身分，從一個 impl sandbox 對該 branch 推送一個新 commit | 記錄 GitHub 在 push 之後是否保留 auto-merge 請求（`gh pr view N --json autoMergeRequest`）。如果有，conductor 的下一輪會對該 story 輸出 `disable-auto-merge`，因為新的 head 還沒有綠的檢查與 review 結論，之後請求就消失了。只有在新的 head 符合資格時才會再次啟用。應該成功（SUCCEED）的是最後這一部分。在 push 與那一輪之間，請求是啟動狀態：記下那段時間有多久 | |

### F. Conductor

| # | Attempt | Expected | Result |
|---|---|---|---|
| F1 | 在 conductor 執行時設定 `CONDUCTOR_PAUSED=true` | 一輪之內它印出 halt、不派發任何東西、不開啟任何 PR。如果某個 open PR 開著 auto-merge，它也會把它關掉（F13） | |
| F2 | 執行 `agentctl conductor --dry-run` | 它列出它將採取的動作，但不執行它們。它不建立任何東西：沒有 issue、label、留言、變數。這一項應該成功（SUCCEED） | |
| F3 | 對一個 stage 正在進行中的 story，執行 `agentctl conductor` 兩輪 | 第二輪不會再次派發已在進行中的 stage | |
| F4 | 對一個 story 加上 label `needs-human` | 下一輪會跳過它，並推進其他 story | |
| F6 | 直接殺掉 conductor（對它的 PID 執行 `kill -9`，或不按 Ctrl-C 就關掉終端機），然後立刻重新啟動 | Lock 不會殘留：新的 conductor 能啟動。它不會再次派發 marker 已在 issue 上的 stage。沒有任何東西遺失 | |
| F7 | 在 story agent 的 sandbox 中，要求 agent 修改 `agentdev.toml` | 被 deny rule 擋下；即使被繞過，該 PR 是 T2，需要你的核准 | |
| F9 | 用 agent 身分偽造 marker。執行 `agentctl conductor --dry-run`，挑一個它計畫派發 `design` 的 story。用 agent 的 token，在它的 issue 上留言：`<!-- conductor {"id":"forged","stage":"design","at":EPOCH_NOW,"harness":"claude","attempt":1} -->`。然後再執行一次 dry run | 該留言被忽略：dry run 仍然計畫對該 story 派發 `design`，和留言之前一樣。由 `[roles] humans` 中列出的人寫下的同一則留言則會被採信，所以測試之後請刪除該測試留言 | |
| F10 | 在一個終端機中執行 `agentctl conductor` 的同時，為同一專案在同一台 Mac 上再啟動第二個 `agentctl conductor` | 第二個立刻以 "another conductor for this project is already running on this Mac" 與 lock 檔的路徑停止。第一個繼續執行。（兩台 Mac 上的兩個 conductor 不受支援，也沒有任何機制阻止：請勿在正在使用的專案上測試） | |
| F11 | 在 conductor 執行時，把 `CONDUCTOR_PAUSED` 設為 `true` | 一輪之內它印出 `halt (kill switch is on)` 並且不派發任何東西。除了關掉有開啟的 auto-merge（F13）之外，它不做其他任何事。把變數設回 `false` 之後，一輪之內就會恢復 | |
| F12 | 在 marker 與送出之間中斷一次派發。在 `conductor.env` 中，把 `CLAUDE_TRIGGER_URL` 指向一個接受連線但永不回應的 `https://` 位址。執行 conductor。一旦留言 "Dispatching ..." 出現在 story issue 上，就用 `kill -9` 殺掉程序。你大約有 30 秒，之後送出會自行放棄。還原 URL 並再次啟動 conductor | Marker 在 issue 上，且沒有 session 啟動。之後的各輪不會再次派發該 stage。在 `[conductor.stage_timeout_minutes]` 中該 stage 的逾時之後，它會被再派發一次，為 attempt 2。任何時候都不會有兩個 session 為同一個 stage 執行 | |
| F13 | 在 auto-merge 已開啟的情況下暫停。以 admin 身分，對一個檢查尚未全綠的 open 測試 PR 啟用 auto-merge：`gh pr merge N --auto --squash`。設定 `CONDUCTOR_PAUSED=true` 並查看該 PR。然後讓 conductor 執行一輪 | 單單設定變數不會改變該 PR：auto-merge 仍然開著。該輪輸出 halt 與 `disable-auto-merge (#N)`。之後 `gh pr view N --json autoMergeRequest` 顯示沒有 | |
| F14 | 暫停讀取失敗。這在真實的 GitHub 上不容易強制發生。它由一個 unit test，以及閱讀 `tools/agentctl/github.py` 中的 `variable()` 來涵蓋：讀取失敗會拋出例外，conductor 隨後的行為如同已暫停。這裡要確認的是 Conductor App 的 token 能讀取 repository 變數。把 `CONDUCTOR_PAUSED` 設為 `false` 並執行 `agentctl conductor --dry-run` | 在輸出中找一行寫著 "treated as paused: cannot read the repository variable ..." 的 `halt`。它不得出現。不要用沒有派發來判斷：沒有事可做的計畫也不會派發任何東西。如果那一行出現了，且帶有 HTTP 403，表示 App 可能無法讀取 repository 變數，而每一輪的行為都會如同已暫停 | |
| F15 | 缺少憑證。挑一個 sprint 指派給 `default`、其下一個 stage 使用 `via = "http"` 或 `"comment"` harness 的 story。從 `conductor.env` 移除它的憑證（`CLAUDE_TRIGGER_URL` 或 `DISPATCH_TOKEN`）並執行 conductor。然後在 sprint 檔中把一個 story 指派給另一位 developer，再執行一次。對於 Claude review，在 `conductor` environment 的 secret `CLAUDE_CODE_OAUTH_TOKEN`（或 `_<LOGIN>`）被刪除的情況下重複一次。事後把一切還原 | 缺少憑證：派發失敗並顯示 "no https trigger URL configured for harness '...'" 或 "no dispatch token configured ..."，有 developer 時會指名該 developer。不寫入任何東西：story issue 上沒有 marker 留言。另一位 developer 的 story：計畫印出 `deferred: story NNN belongs to ...; this conductor runs for ...`，且不寫入任何東西。缺少 review secret：workflow 會啟動（這個 conductor 看不到 GitHub 的 secret），review 步驟失敗，head commit 上的 `agent-review` 是 failure。對具名 developer，它絕不會使用純名稱的 secret 執行 | |
| F16 | 在 sandbox 中的本機 Codex review。對一個其 review stage 以 `via = "sbx"` 執行 Codex 的 story，讓 conductor 派發 review。做兩次：一次是審查身分的登入帳號不在 repository 變數 `REVIEW_BOTS` 中，一次是它在其中。第二次觀察需要一個新的 head commit，或第一次 review 的結論：第一次派發留下了一個 marker，而這個 marker 會改變下一輪的行為 | 只有在提交 review 的身分的登入帳號被列在 `REVIEW_BOTS` 中時，review 才會到達 `agent-review` status。不在其中：review 出現在 PR 上，且不寫入任何 status。在其中：`bridge` job 把 status 寫在被審查的 commit 上，這一部分應該成功（SUCCEED）。記下你實際看到的登入帳號 | |
| F17 | 在 conductor 於另一個終端機中執行的同時，執行 `agentctl conductor --dry-run` | 它執行一輪、印出計畫並結束，不等待也不干擾 lock。執行中的 conductor 不受影響，也不建立任何東西。這一項應該成功（SUCCEED） | |
| F18 | 連續三輪失敗。對一個該派發的 story，把 `conductor.env` 中的 `CLAUDE_TRIGGER_URL` 設為一個拒絕連線的 `https://` 位址，並啟動 conductor。事後還原 | 每一輪都為該派發印出 `FAILED: ...`（且 issue 上不留下 marker）。連續第三次之後，它印出 "3 passes in a row failed; next pass in 15 minutes"。URL 還原後，下一個成功的那一輪使它回到正常的間隔 | |
| F19 | 缺少設定。把 `conductor.env` 改名並執行 `agentctl conductor` | 它立刻以一則指出該檔案與缺少的 key 的訊息停止。它不開始任何一輪 | |
| F20 | Conductor 讀取 default branch。在你的工作目錄中，編輯使用中的 sprint 檔（例如加一個 story），不要 commit 或 push，然後執行 `agentctl conductor --dry-run`。接著 checkout 另一個 `agentdev.toml` 不同的 branch，再執行一次 | 兩次的計畫都反映 `origin/main`：未 commit 的 story 不會被規劃，另一個 branch 的設定也不會被使用 | |
| F21 | 睡眠。在 conductor 執行、且有一個 stage 在雲端進行中時，讓 Mac 睡眠超過該 stage 的逾時，然後喚醒 | 睡眠期間不會派發任何東西。喚醒後，下一輪依一般規則處理停滯的 stage：若它從未回報就再派發為 attempt 2，若它已回報就不派發。記下發生了什麼 | |
| F22 | Spec 起草上限。在 `main` 上的 roadmap 放四個未勾選的行，且沒有任何 spec pull request 開著 | Conductor 一次只派發一個 product-owner stage，且絕不會讓超過 `max_open_spec_prs` 個未核准的 spec pull request 開著 | |
| F23 | 擱置太久。擱置一個 story（triage 新增了對一個未完成 story 的依賴），並讓它放過 `max_parked_hours`（測試時把它設為 1） | 該 story 被加上 `needs-human` label，並有留言說明它已等待所指名的 story 超過那麼多小時。它被升級一次，不是每一輪都升級 | |
| F24 | Session 上限。把 `max_dispatches_per_story` 設為 3，並讓一個 story 用掉三個 session 而未完成 | 當它要啟動第四個時，它以 "3 sessions without finishing" 被升級。移除 `needs-human`：在下一次升級之前，它再得到三個 session | |
| F25 | 等待被升級者。升級 story A，同時 story B 依賴它（透過 triage 的依賴） | A 上的留言以 "Waiting for it: B." 結尾。B 沒有被標上 `needs-human`。你解決 A 之後，B 恢復 | |
| F26 | 提醒。讓一個 story 停在 `needs-human`（或一個未核准的 T2 PR）超過 `remind_after_hours`（把它設為 1） | 在 sprint issue 上再被提及一次，每次等待一次。如果每個未完成的 story 都在等待，「sprint stalled」通知仍然會出現 | |
| F27 | 回來的 story。擱置兩個 touch 同一樣東西的 story，其中一個有 session 在執行，然後滿足其依賴 | 有執行中 session 的那一個先被接納並保有它的占用；另一個不會與它並行啟動 | |
| F28 | 清除被擱置的 story。讓 F23 升級一個被擱置的 story，然後移除 `needs-human` | 在再過 `max_parked_hours` 之前，它不會再次被升級 | |

## 5. 尚未驗證

這一層的任何東西都沒有對真實的 GitHub、各家廠商的雲端服務、Docker Sandboxes 或 Mac 執行過。最可能出現意外的地方：

- `tools/agentctl/github.py` 中 `collect` 與 `execute` 對真實 API 的全部行為：`statusCheckRollup`、`reviewDecision`、`autoMergeRequest`、issue 依賴（`blocked_by`）的形狀，以及 GitHub 回報的檢查名稱。Conductor 會去掉 `<caller job> / <job>` 中 caller 的部分。
- GitHub 是否會在 push 之間保留 auto-merge 請求，以及以 Conductor App 身分使用 `--disable-auto` 與 `--match-head-commit`（D22，第 3.10 節）。
- Conductor App 的 token 是否能讀取 repository 變數並派發 workflow（F14），以及 `CONDUCTOR_PAUSED` 是否能只建立一次並被可靠地讀取。
- 每家廠商哪條雲端路徑可行：Claude Code on the web 的 scheduled task API trigger（`via = "http"`），以及啟動 Codex cloud task 的 mention（`via = "comment"`），包括該留言必須來自與 cloud task 連結的帳號。Spike 會決定這一點；對不可行的路徑，使用 `via = "sbx"`。
- `agent-review` workflow 路徑，以及 review bot 的 review 的登入帳號與格式（[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)）。
- 本機 sandbox 路徑（`agentctl sandbox job`）：Docker Sandboxes 的行為、每個 stage 一個全新的 sandbox，以及之後的移除（[layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)）。
- Agent 自己的行為：它們是否會加上 `done:*` label、在 stage 結束時只推送一次，並停留在它們的 prompt 範圍內。這些 prompt 尚未試過。
- 時間：stage 逾時，以及 180 秒的一輪對上 GitHub 的 rate limit。
- guideline 中分鐘數表格的數字。

## 6. 已知限制

- **一個 conductor，在一台 Mac 上。** Lock 檔使同一台 Mac 上的第二個 conductor 無法啟動。另一台 Mac 上的第二個 conductor 不受支援，也沒有任何機制阻止它。兩個 conductor 可能把同一個 stage 派發兩次（但絕不會遺失一個：marker 是先寫的）。
- **Mac 睡眠或終端機關閉時，沒有任何東西會前進。** 雲端上沒有 conductor、沒有交接，也沒有它已停止的通知。已派發到雲端的工作會繼續，下一輪會依 stage 逾時發現停滯。
- **有多位 developer 時，一個 conductor 不派發其他人的 story。** 指派給另一個登入帳號的 story 會等到那個人的 Mac 上有 conductor 執行。`via = "sbx"` 的 stage 只會在該 story 所屬 developer 的 Mac 上啟動。
- **Conductor 的金鑰在 host 上。** Conductor App 的私鑰放在你的 Mac 上、專案目錄之外，任何 sandbox 都看不到，但它在 host 上。任何能存取你帳號的人都能使用它。
- **編輯 caller workflow 的 pull request 會選擇審判它的 workflow。** 對 `pull_request` 事件，GitHub 執行該 PR 自己的 workflow 檔，所以被更改的 `uses:` 或 `kit_version:` 決定了由哪個 kit 產生該 PR 的檢查結果。防禦手段是 `.github/**` 上的 CODEOWNERS 與你閱讀 diff；這種 PR 上的綠色檢查所能說明的很少（[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)）。一個值得評估的緩解方式是 GitHub 的 ruleset 規則 "require workflows to pass"，它會執行來自固定 repository 與 ref 的 workflow，而不是 PR 的副本。它在 Team plan 上是否可用尚未驗證。
- **Sandbox 啟動的程式碼仍在改寫中。** 當 `sbx create` 或 `sbx secret set` 失敗時 `sbx.sh job` 的狀態，見 [layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)。
- **格式錯誤的 `CONDUCTOR_QUOTA` 會逐項被忽略。** 一個壞掉的項目表示該 harness 被視為有額度；不會有任何通知。請讓這個變數保持為有效的 JSON。
- **Network probe 無法區分來源端自己的 403 或 5xx 與政策封鎖**，所以 sandbox 啟動檢查可能回報一個其實不是封鎖的封鎖，或相反。見 [layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)。
- **`touches` 是一種預測，一定會有遺漏。** 代價是 merge conflict 與重工，事後由 triage 與 conflict 解決 stage 修正。它不會導致錯誤的程式碼被 merge。
- **產能受訂閱額度限制。** 額度用盡時，工作會變慢；它不會失敗。Conductor 不會從廠商讀取額度：你要手動設定 `CONDUCTOR_QUOTA`。
- **雲端觸發依賴兩家廠商仍在變動的功能。** Fallback 是本機 sandbox，這需要 Mac 開著且 conductor 在執行。
- **Conductor 的登入帳號無論有沒有 `[bot]` 後綴，都被接受為 marker 作者。** 登入帳號等於 Conductor App slug 的人會被採信為 marker 作者。他們同時也必須是該 repository 的 collaborator，才能留言。
- **你不在時，決定會累積。** 等你處理的事（T2 pull request、升級、spec、sprint）是系統中唯一由你決定節奏的部分。
- **Actions 用量是估計值**，且額度不會被自動延長（[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)）。
