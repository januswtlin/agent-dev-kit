# 建立新專案

*English: [new-project.md](new-project.md)。兩份內容不一致時以英文版為準。*

每個專案做一次，由管理 GitHub organization 的人執行。做完之後，專案就可以讓人加入。

每個人之後在自己電腦上要做的事在 [new-machine-zh-TW.md](new-machine-zh-TW.md)。專案的日常運作在 [operations-zh-TW.md](operations-zh-TW.md)。

標示 **待驗證** 的地方還沒在真實的帳號或機器上跑過。做的時候請對照當下的官方文件，並把結果回寫到這份文件。

請依章節順序做。每一節都依賴前面的章節。

如果你是專案的第一個人，跨這兩份設定文件的順序是：

1. 這份文件的第 1 到第 5 節：repo、conductor 的身分、secrets 與 variables、rulesets。
2. [new-machine-zh-TW.md](new-machine-zh-TW.md) 的全部：你的 agent 身分、你的 secret、你的 sandbox、你的雲端帳號。它需要第 1 到第 5 節所建立的 repo、`conductor` environment 與 clone。
3. 回到這裡做第 7 節（spike）、第 8 節與第 9 節。

## 1. 需要什麼

- GitHub organization，方案要能在 private repo 上強制 ruleset（Team 以上），每個人一個座位。Agent 與 conductor 都是 GitHub App，不佔座位。
- 執行這些步驟的電腦上要有 Python 3.11 以上。工具使用 `tomllib`，並以 `python3 -I` 啟動。檢查：

```bash
python3 --version
```

- 較新版的 `gh`，並以 repo admin 身分登入。Conductor 與 script 會用到 `gh variable get` 與 `gh variable set`，舊版沒有這兩個指令。目前不知道確切的最低版本。下面這行若印出用法說明，表示你的 `gh` 夠新；若回報未知指令，請升級：

```bash
gh variable get --help
```

- 能以你的身分經由 HTTPS push 到 GitHub 的 `git`。第 2 節會 push 到 `main` 一次，spike 會 push 一個 branch。如果你還沒有設定好，就讓 `gh` 來做：

```bash
gh auth setup-git
```

## 2. 建立專案 repo

在 organization 下建立新的 private repo，讓它的 `main` branch 上是這個 template 的內容，並放在你 Mac 上不受 iCloud 同步的位置。`OWNER/REPO` 是新的 repo；`TEMPLATE_OWNER/agent-dev-template` 是你取得這個 template 的地方。

如果 template repo 在 GitHub 上被標記為 template，而且它的 `main` branch 上有這些檔案：

```bash
mkdir -p ~/dev && cd ~/dev && gh repo create OWNER/REPO --private --template TEMPLATE_OWNER/agent-dev-template --clone
```

否則（例如 template 的內容還在一個尚未合併的 branch 上），就自己複製那個 branch。`TEMPLATE_BRANCH` 是放著這些檔案的 branch：

```bash
mkdir -p ~/dev && cd ~/dev && git clone --branch TEMPLATE_BRANCH https://github.com/TEMPLATE_OWNER/agent-dev-template REPO
```

```bash
cd REPO && gh repo create OWNER/REPO --private && git remote set-url origin https://github.com/OWNER/REPO.git
```

```bash
git branch -M main && git push -u origin main
```

不論是哪一種，都進入 clone 下來的目錄，並確認它是 template 而不是空的 repo。之後的每個指令都在這裡執行：

```bash
cd ~/dev/REPO && ls AGENTS.md policy/roles.toml sandbox/sbx.sh
```

填入專案裡有誰。第一個帳號是 director，負責核准產品決定；列出的每個帳號都可以核准 T2 變更。只有一個人也可以：

```bash
scripts/init.sh DIRECTOR_LOGIN OTHER_LOGIN
```

接著打開 `policy/roles.toml`，為每個人設定哪個 harness 負責哪個 stage。檔案裡有單一廠商、兩家廠商、加上本地模型的範例。

確認：

```bash
make lint && make test
```

`scripts/init.sh` 只修改本機的檔案（`.github/CODEOWNERS` 與 `policy/roles.toml`）。把它們 commit 並 push 到 `main`：

```bash
git add .github/CODEOWNERS policy/roles.toml && git commit -m "Fill in who is on the project" && git push origin main
```

這次 push 會在 `main` 上啟動 `ci` workflow。等它跑完並確認是綠的；這是之後每個 pull request 用來比較的基準，而第 5 節會讓這些 check 成為強制要求：

```bash
gh run list --workflow ci.yml --branch main --limit 1
```

如果是紅的，現在就用另一次直接 push 修好。第 5 節之後，修正就需要 pull request。

這是唯一一次直接 push 到 `main`，而且必須現在做，在第 5 節的 ruleset 存在之前。Ruleset 套用之後，`main` 只能經由 pull request 變更，而動到這兩個檔案的 pull request 需要 code owner 的核准，也需要 `main` 上的 `policy/roles.toml` 所列的人類核准。只要 `main` 上還留著佔位字串 `DIRECTOR_LOGIN`，就沒有人是 code owner，也沒有人是那樣的人類，所以沒有人能核准修正它的 pull request。

## 3. 專案的身分

專案本身有兩種身分：conductor，以及人。每個人的 agent 身分屬於他自己，在 [new-machine-zh-TW.md](new-machine-zh-TW.md) 設定。

### Conductor GitHub App

Conductor 會開啟並合併 pull request、在 issue 上留言與加 label、觸發 workflow、讀取 check，以及讀寫 repository variable。在 organization 的 Settings > Developer settings > GitHub Apps 建立一個 App：

- Repository permissions：Contents: Read and write；Pull requests: Read and write；Issues: Read and write；Actions: Read and write；Variables: Read and write；Checks: Read；Commit statuses: Read；Metadata: Read。
- 不訂閱任何 webhook，取消勾選 Active。
- 建立後產生一把 private key，並把 App 安裝到這個 repo。記下 App 的數字 ID。下載的 key 檔要放在專案目錄之外：sandbox 讀得到該目錄裡的每個檔案，包含被 git 忽略的檔案。

接著建立存放 pipeline secret 的 GitHub environment。請在設定 `CONDUCTOR_APP_ID` 之前做：這個 variable 是空的時候，conductor 的 job 會被跳過，而它不應該在 environment 受到限制之前執行。

1. 在 repo 的 Settings > Environments，建立一個名稱正好是 `conductor` 的 environment。
2. 在 Deployment branches and tags 選 Selected branches and tags，加入一條只允許 default branch（`main`）的規則。
3. 在這個 environment 裡新增 environment secret `CONDUCTOR_APP_PRIVATE_KEY`，值是 private key 的完整內容。也可以用指令：

```bash
gh secret set CONDUCTOR_APP_PRIVATE_KEY --env conductor < PATH_TO_PRIVATE_KEY.pem
```

為什麼用 environment 而不是 repository secret：持有憑證的 job（`conductor.yml` 的 `reconcile`、`brief.yml` 的 `brief`、`agent-review.yml` 的 `claude`）都宣告了 `environment: conductor`。從其他任何 ref 啟動的執行，包含手動 dispatch 某個 branch，GitHub 本身就會拒絕給它 secret。Repository secret 沒有這種規則。**待驗證**：Team 方案的 private repo 是否能使用帶有 deployment branch 規則的 environment、這些設定的確切名稱，以及若 workflow 先提到這個 environment，GitHub 不會自動建立一個沒有 branch 規則的 environment。

最後，在 repo 的 Settings > Secrets and variables > Actions > Variables 新增 repository variable，或執行：

```bash
gh variable set CONDUCTOR_APP_ID --body APP_ID
```

從這一刻起，conductor 在 GitHub Actions 上執行。它還沒有任何東西可以派發：template 的 sprint 檔（`docs/sprints/000.toml`）沒有列出任何 story。不過，任何 push 到 `story/`、`spec/`、`sprint/` 或 `chore/` 底下的 branch，它都會為之開啟 pull request。在第 5 節完成、而且有一個人做完 [new-machine-zh-TW.md](new-machine-zh-TW.md) 之前，不要合併列有 story 的 sprint 檔。

| 類型 | 名稱 | 位置 | 值 |
|---|---|---|---|
| Environment secret | `CONDUCTOR_APP_PRIVATE_KEY` | Environment `conductor` | private key 的完整內容 |
| Repository variable | `CONDUCTOR_APP_ID` | Settings > Secrets and variables > Actions > Variables | App 的數字 ID |

### 人類

專案裡的每個人都是 repo admin。Organization 的 Settings > Actions > General 中，確認 **Allow GitHub Actions to create and approve pull requests** 是關閉的。

## 4. Secrets 與 variables

兩個不同的地方：

- **Secret** 是 `conductor` 這個 environment 的 environment secret（Settings > Environments > conductor）。上面的 `CONDUCTOR_APP_PRIVATE_KEY` 是如此，每個屬於個人訂閱的 secret 也是如此（`DISPATCH_TOKEN`、`CLAUDE_CODE_OAUTH_TOKEN`、`CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN`，sprint 檔交給指名的人的 story 則要帶 `_LOGIN` 後綴）。後者的說明在 [new-machine-zh-TW.md](new-machine-zh-TW.md) 第 3 節。不要把其中任何一個建成 repository secret：job 讀的是 environment，而 repository secret 連從 branch 執行的 workflow 也讀得到。
- **Variable** 是 repository variable（Settings > Secrets and variables > Actions > Variables）。裡面不放任何機密。專案的 variable 如下：

| 類型 | 名稱 | 來源 | 何時需要 |
|---|---|---|---|
| Variable | `REVIEW_BOTS` | JSON 陣列，列出哪些帳號的 pull request review 算作 agent review，例如 `["chatgpt-codex-connector[bot]"]` **待驗證**。如果某個 review stage 在本機 sandbox 執行（`via = "sbx"` 而且沒有 `review_workflow`），也要把那位開發者的 agent App 帳號加在這裡，例如 `"yourname-agent[bot]"`：sandbox 的 token 無法自己寫入 status，所以它的 review 由 `bridge` job 轉換，而 `bridge` job 只聽這些帳號的 | Codex review；在本機 sandbox 執行的 review |
| Variable | `CONDUCTOR_PAUSED` | 要暫停時設為 `true`；否則設為 `false` 或不設 | Kill switch |
| Variable | `CONDUCTOR_QUOTA` | JSON，例如 `{"alice/codex": 1795800000}`，值為額度恢復的 epoch 秒 | 手動標記某個 harness 額度用盡 |
| Variable | `OLLAMA_MODEL` | 例如 `devstral` | 使用 Ollama 時 |
| Variable | `LIGHT_RUNNER` | 1-core runner 的 label **待驗證**；不設則用 `ubuntu-latest` | 想降低輕量 job 的費用時 |
| Variable | `CI_RUNNER` | 由 `agentctl budget` 自動維護，不需手動設定。Overflow 預設關閉，所以它會一直是 GitHub-hosted runner | `ci` 與 `security` 在哪裡執行 |
| Variable | `CONDUCTOR_HOME`、`CONDUCTOR_LEASE`、`ACTIONS_USAGE` | 由 `agentctl` 自動維護 | Conductor 的位置與用量估算 |
| Variable | `CONDUCTOR_BOT` | 通常不設。不論在 Actions 上或在本機，conductor 都會從 App 得出自己的帳號（`APP-SLUG[bot]`）。放進這個 variable 的帳號會被額外信任為 conductor marker 留言的作者 | 只有在以另一個帳號寫下的 marker 仍須被採信時才需要。列在這裡的帳號可以左右 conductor，所以其他情況請不要設 |

## 5. Rulesets 與 repo 設定

Template 的內容與第 2 節的 commit 必須先在 `main` 上（required checks 對應的 workflow 要存在，code owner 也要是真實的帳號），而且 `main` 上的 `ci` 執行必須是綠的（第 2 節），再套用 ruleset。以 admin 身分執行，並帶上 Conductor App 的數字 ID：

```bash
CONDUCTOR_APP_ID=APP_ID scripts/apply-rulesets.sh
```

沒有 `CONDUCTOR_APP_ID` 時 script 會拒絕執行。它會建立或更新三個 ruleset：

- `main`：不可刪除、不可 force-push、只能經由 pull request 變更（需要 code owner review 的路徑要有該 review），以及五個 required check。任何人都沒有 bypass。
- `main-merge`：只有 repo admin 與 Conductor App 可以更新 default branch。Agent 的 token 可以 push branch，而這個 ruleset 讓它即使在 pull request 的每個 check 都是綠的時候也無法合併。Admin 與 Conductor App 仍然必須滿足 `main` 的全部要求。
- `release-tags`：只有 repo admin 可以建立、移動或刪除 `v*` tag。

在 Settings > General > Pull Requests：開啟 Allow auto-merge、只允許 squash merging、開啟 Automatically delete head branches。Allow auto-merge 不是選用的：code owner 核准 spec 或 sprint 的 pull request 之後，conductor 會在它的下一輪替這個 pull request 啟用 auto-merge，合併靠的就是這個。不論 `auto_merge_tiers` 怎麼設它都會這樣做，因為這個決定是人做的。它絕不會對 `chore/` 的 pull request 這樣做；那些由人來合併。

確認：

```bash
gh api repos/OWNER/REPO/rulesets --jq '.[].name'
```

應列出 `main`、`main-merge` 與 `release-tags`。**待驗證**：`.github/rulesets/*.json` 的欄位是否被目前的 API 接受；`main` 與 `main-merge` 是否如上所述疊加（`main-merge` 的 bypass 不會削弱 `main`）；App 的 ID 是否就是 Integration bypass 該用的 `actor_id`；以及 `main.json` 裡的 `integration_id: 15368` 是否就是產生 required check 的 GitHub Actions app。若 API 回報未知欄位，依錯誤訊息調整後回寫。

## 6. 設定第一個人

做 spike 之前，至少要有一個人把 [new-machine-zh-TW.md](new-machine-zh-TW.md) 從頭到尾做完：他的 agent 身分、他的 secret、他的 sandbox、他的雲端帳號。現在就去做，做完再回到這裡。

## 7. Spike：先證明一圈跑得完

在投入真正的 story 之前，用一個玩具 story 驗證整條路徑。Spike 就是 sprint 001。目標是除了這裡列出的指令之外，不下任何手動指令，就看到這個順序發生。

沒有人手動開 pull request。Agent（在這裡是你）push 一個 branch。Workflow `notify` 會在這次 push 時執行；它不持有任何 secret，也不做任何事。Conductor 在它完成時做出反應，以 Conductor App 的身分開啟 pull request。你自己開的 pull request，你無法核准。

1. 在名為 `sprint/001` 的 branch 上建立 spike 的 spec 與 sprint：

```bash
git switch -c sprint/001
```

```bash
cp -R docs/specs/_template docs/specs/001-hello
```

```bash
cp docs/sprints/_template.toml docs/sprints/001.toml
```

   填好三個 spec 檔（一個 AC、兩個 TC 的小功能）與 sprint 檔（`stories = ["001"]`）。至於 `assignee`，若第 6 節那個人的 secret 是用不帶後綴的名稱存的（`DISPATCH_TOKEN`），就保留 `default`。只有在他的 secret 帶有後綴（`DISPATCH_TOKEN_ALICE`）時，才把它設為他的帳號：交給指名的人的 story 使用那個人帶後綴的 secret，絕不會退回去用不帶後綴的。

   這個玩具功能請用 Python 寫。依 template 原本附帶的設定，`make test` 會對 `tests/` 目錄執行 Python 的 `unittest`，並寫出 gate 所讀取的結果檔，所以 spike 不需要其他的 test runner。測試把它的 TC id 放在名稱裡，例如 `test_tc_001_01_says_hello`。要使用別的技術組合，先在 `chore/` branch 上修改 `Makefile` 的 `project-*` target 並合併，讓 runner 在 story 開始之前就已經在 `main` 上；red-green 會在 `main` 上執行這個 story 的測試。

   然後檢查、commit 並 push：

```bash
make lint
```

```bash
git add docs/specs/001-hello docs/sprints/001.toml && git commit -m "Add the spike story and sprint 001" && git push -u origin sprint/001
```

2. 等 conductor 為 `sprint/001` 開啟 pull request。它一開就是可審狀態。等到 `ci`、`security`、`spec-verify` 與 `agent-review` 都是綠的。`risk-gate` 這時候是紅的，這是正確的：spec 與 sprint 檔是 T2，而 `risk-gate` 要等 `policy/roles.toml` 所列的人核准了目前的 commit 才會通過。
3. 暫停 conductor。否則 sprint 檔一合併就會立刻開始一次真正的執行。這也表示 conductor 不會替你合併這一個 pull request：暫停中的 conductor 不派發任何東西、不開任何東西，也不啟用 auto-merge：

```bash
gh variable set CONDUCTOR_PAUSED --body true
```

4. 核准這個 pull request。`risk-gate` 會因你的 review 重新執行並轉綠。然後自己合併它，只有這一次。合併會觸發 conductor 執行；暫停期間每一次都只印出 `halt`：

```bash
gh pr merge sprint/001 --squash
```

5. 要求一次 dry run。暫停期間它同樣只印出 `halt (kill switch is on)`，因為暫停中的 conductor 不會計算計畫。這可以確認 kill switch 有效：

```bash
gh workflow run conductor.yml -f dry_run=true
```

6. 要看到計畫，就解除暫停並立刻要求一次 dry run。解除暫停本身不會啟動任何東西：下一次真正的執行要等下一個事件，或排程的執行（每四小時一次）。如果中間剛好有事件進來，真正的執行會先發生；在這裡沒有害處。

```bash
gh variable set CONDUCTOR_PAUSED --body false
```

```bash
gh workflow run conductor.yml -f dry_run=true
```

   閱讀執行紀錄。它應該列出為 story 001 派發 `design`，沒有其他意外的動作。Dry run 不會建立任何東西，連追蹤用的 issue 也不會。
7. 啟動真正的執行：

```bash
gh workflow run conductor.yml
```

8. Conductor 派發 `design`。Agent push `story/001-hello`，`notify` 執行，conductor 以 draft 開啟 pull request。Draft 只跑 lint 與 `risk-gate`。
9. 依序出現 `done:design`、`done:tests`、`done:impl`。`done:impl` 之後 conductor 把 pull request 轉為可審，完整的 gate 第一次執行。
10. `agent-review` 針對 head commit 被派發，並把 status 寫在它上面。沒有完成的 review 會被發布為 failure，絕不會留成通過。如果 branch 在 review 等待開始的期間有了變動，那次執行會不產生結論就停止，conductor 會要求對新的 commit 做 review。
11. 五個 check 全綠，而且 head commit 上還帶有一個名為 `risk-tier/T1`（或 `T0`）的 status：conductor 依據的是這個 status，不是 `tier:` label。Shadow mode 下 conductor 通知你這個 pull request 可以合併；你按 merge。
12. `evidence` 把對照表貼到 story issue。

Claude 與 Codex 各擔任一次實作。每一步若卡住，記下卡在哪裡與錯誤訊息：

| 卡住的地方 | 處理 |
|---|---|
| Conductor 讀狀態時出錯 | 修 `tools/agentctl/github.py` 的 `collect`。它還沒對真實 API 跑過 |
| `reconcile` job 在 App token 那一步失敗，或被拒絕使用 environment | 檢查 environment `conductor` 是否存在、它的 branch 規則是否允許 `main`，以及 `CONDUCTOR_APP_PRIVATE_KEY` 是這個 environment 的 secret，而不是 repository secret |
| Branch 已 push，卻沒有出現 pull request | 檢查 `notify` 是否因這次 push 而執行，之後是否接著有一次 `conductor` 執行。`CONDUCTOR_PAUSED` 為 `true` 時 conductor 不會開任何東西，一天也不會開超過 `max_prs_per_day` 個 story pull request。Branch 名稱必須以 `story/`、`spec/`、`sprint/` 或 `chore/` 開頭 |
| Pull request 開了但 check 沒跑 | 它必須由 Conductor App 開啟，不是用 `GITHUB_TOKEN`。檢查 `reconcile` job 是否用了 App token。另外，check 只會為目標是 `main` 的 pull request 執行 |
| 已核准的 spec 或 sprint pull request 沒有合併 | Conductor 是在核准之後的下一輪才啟用 auto-merge，不是在你核准的那一刻。檢查你的 review 之後是否接著有一次 `conductor` 執行（在 Actions 上是由 `risk-gate` 重新執行所啟動）、conductor 沒有被暫停、Allow auto-merge 是否開啟（第 5 節）、核准是否來自 code owner，以及五個 check 在你核准的那個 commit 上是否全綠。核准之後再有 push，核准就失效。`chore/` 的 pull request 絕不會由 conductor 合併：請自己合併 |
| 某個 harness 無法由雲端觸發 | 在 `policy/roles.toml` 把它改成 `via = "sbx"`。它的 stage 會改在開發者 Mac 上的 Docker Sandbox 執行，並等到那台 Mac 上有 `bin/agentctl conductor here` 在跑。這是在 `chore/` branch 上的 T2 變更 |
| Agent 沒有加 `done:*` label | 檢查 agent 身分是否有 Issues 寫入權；必要時在 prompt 中加強 |
| `agent-review` 一直 pending | 如果是 Claude review，看 `agent-review` workflow 的執行：review 沒有完成時 `publish` job 會設成 failure，所以 pending 表示這次執行根本沒有開始、無法解析 pull request，或因為 branch 有了變動而停止（這時 conductor 會再要求一次）。檢查 `CLAUDE_CODE_OAUTH_TOKEN` 是 `conductor` environment 的 secret，`default` 的 story 用不帶後綴的名稱，交給指名的人的 story 則帶帳號後綴；並檢查 action 的輸入參數（包含 `--tools`）。如果是 Codex review，或在本機 sandbox 執行的 review，檢查 `REVIEW_BOTS` |
| 派發失敗，訊息是針對某位指名的開發者的「no dispatch token configured」或「no https trigger URL configured」 | Sprint 檔把這個 story 交給那個人，所以只會使用他帶後綴的 secret。把它加進 `conductor` environment，或把 story 交給 `default` |
| `spec-verify` 在「Keep only plain result files」失敗 | 結果 artifact 裡有 symbolic link。看測試步驟在 `reports/` 底下寫了什麼 |
| Red-green 失敗，訊息是「its test did not run on base」 | 在 `main` 上執行測試時，沒有納入這個 story 的測試檔。檢查 `policy/project.toml` 的 `test_paths`，以及 TC id 是否在測試的名稱裡 |
| Story pull request 是綠的，它的 tier 也在 `auto_merge_tiers` 裡，conductor 卻一直沒有替它啟用 auto-merge | 它從 `risk-gate` 寫入的 commit status `risk-tier/T?` 讀取 tier。檢查這個 status 是否在 head commit 上 |

同時記下這些數字並回填 guideline 第 6 節的表：測試套件跑一次的分鐘數、一個 story 從開始到合併觸發了幾次完整的 gate、Actions 的 Usage 頁面顯示這個 story 用掉多少。

## 8. Red-team

執行 [redteam-project-zh-TW.md](redteam-project-zh-TW.md) 的全部項目。有任何一項沒有得到預期結果，就先修。

## 9. 第一個真正的 sprint

Spike 用掉了 sprint 001，所以第一個真正的 sprint 是 sprint 002。

1. 在 `docs/product/roadmap.md` 加幾行需求，經 PR 合併；或用 PO chat 逐一討論。
2. PO 為每個 story push 一個 `spec/` branch，conductor 開啟 pull request。核准它。核准就夠了：conductor 會在下一輪啟用 auto-merge，check 全綠之後 pull request 就會合併。
3. Planner 會在 sprint 接近完成時起草下一個 sprint。第一個真正的 sprint 需要手動請它起草：開一個 Claude Code session，要它依 `prompts/planner.md` 起草 sprint 002。
4. 核准 sprint 的 pull request。它以同樣的方式合併，conductor 從這裡接手。

Story pull request 的自動合併一開始是關閉的（shadow mode）。何時以及如何開啟，見 [operations-zh-TW.md](operations-zh-TW.md) 第 2 節。
