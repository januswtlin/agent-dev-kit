# 採用 kit

*English: [adopting.md](adopting.md)。兩份內容不一致時以英文版為準。*

如何在新專案與既有專案中開始使用 kit、如何升級，以及如何移除。設計在 [guideline-zh-TW.md](guideline-zh-TW.md)。各層的步驟與測試該層的 checklist，在 [layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)、[layer-2-github-zh-TW.md](layer-2-github-zh-TW.md)、[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md) 與 [layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)。這裡的內容目前都還沒有在真實的 GitHub、Docker Sandboxes 或 Mac 上執行過，所以請依照下面的順序，並在依賴某一層之前先完成該層的 checklist。

## 1. Before you start

你需要：

- 一台 Mac，供 layer 1 與 4 使用。Layer 2 與 3 是 GitHub 設定與 workflow，除了要執行一次 `agentctl` 之外，不需要 Mac。
- 專案的 GitHub repository。私有 repository 需要 Team 方案才能使用 ruleset。
- AI 訂閱：Claude Code 或 Codex，或兩者皆有。不需要 API key。
- `git`、`python3`（3.11 或更新版本，因為需要 `tomllib`），以及以 repository admin 身分登入的 GitHub CLI `gh`。

決定誰是 **director**：他的核准對 spec、sprint 與護欄變更算數。只有一個人時，就是你。

## 2. Install the kit once per Mac

clone kit 並安裝你要的版本。請選你已審閱過的 commit，不要用最新的 tip：

```bash
git clone https://github.com/januswtlin/agent-dev-kit.git
```

```bash
cd agent-dev-kit
```

```bash
./install.sh
```

`./install.sh <ref>` 會安裝這個 clone 的另一個 commit、branch 或 tag。版本以完整的 commit SHA 存放在 `~/.local/share/agent-dev-kit/versions/<sha>/` 之下並設為唯讀，`agentctl` launcher 會放到 `~/.local/bin`。如果安裝程式有提示，請把該目錄加入你的 `PATH`。請讀取被安裝的 SHA；你會在專案中 pin 它。

launcher 從專案選擇 kit 版本。它讀取專案預設 branch 上 `agentdev.toml` 的 `[kit] version`（以最近一次 fetch 為準），絕不從 working tree 讀取。在專案的預設 branch 有那個檔案之前，請明確告訴它要用哪個版本：

```bash
export AGENTDEV_KIT_VERSION=<sha>
```

pin 進入預設 branch 之後就取消設定，讓專案的 pin 發揮作用。

## 3. A new project

1. 建立 repository 並 clone。clone 要放在 iCloud 同步的資料夾之外，例如 `~/dev/project`。
2. 預覽 init 會做什麼：

   ```bash
   agentctl init --dry-run DIRECTOR_LOGIN
   ```

3. 執行它。第一個 login 是 director；其餘的 login 是其他在 T2 變更上核准算數的人：

   ```bash
   agentctl init DIRECTOR_LOGIN
   ```

   它會把 `templates/project/` 複製到專案中：`agentdev.toml`、caller workflow `.github/workflows/agentdev-*.yml` 與 `release.yml`、issue 與 pull request 範本、`AGENTS.md` 與 `CLAUDE.md`、`.claude/` 底下內嵌 kit prompt 的 agent 檔案、`Makefile`、docs 骨架（product、spec 與 sprint 範本、design）以及產生的 `.github/CODEOWNERS`。它會填入 kit 版本（它所執行的已安裝 kit 的 SHA，或 `--kit-version`）、kit 的 repository 與相關人員。
4. 開啟 `agentdev.toml`，設定專案的實際值：`[tests]` 依技術堆疊設定（指令，以及 JUnit XML 的寫入位置）、`[risk.t2] high_risk` 依專案的結構設定、`[stories] translation`（預設 `"zh-TW"`；只用英文則設為 `""`）。`agentctl config KEY` 會印出某項設定。`Makefile` 一開始使用 Python 的 unittest，並說明如何切換到 pytest、vitest、node 或 Go。
5. 在 branch 上 commit，開 pull request 並 merge。第一次 merge 由你自己完成，此時 ruleset 還不存在。pin 進入預設 branch 之後，取消設定 `AGENTDEV_KIT_VERSION`。
6. 依序採用各層，每一層的 checklist 完成後才進行下一層：
   1. [layer-1-isolation-zh-TW.md](layer-1-isolation-zh-TW.md)
   2. [layer-2-github-zh-TW.md](layer-2-github-zh-TW.md)
   3. [layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md)
   4. [layer-4-conductor-zh-TW.md](layer-4-conductor-zh-TW.md)，從 shadow mode 開始

對新專案而言，四層全部採用是目標。你可以在任何一層之後停下來：每一層單獨都有用，而後面的層依賴前面的層（指南第 3 節）。

## 4. An existing project

既有專案有自己的檔案、測試、issue 與習慣。kit 絕不覆寫它們，也不會要求專案重新命名任何不必要的東西。

### Order

1. **先做 layer 1 與 2。** 它們加入保護，但不改變專案如何 build 或測試：為 agent 提供隔離，並以 ruleset 與 CODEOWNERS 使 agent 無法更改規則或 merge。兩者都不要求專案的測試處於任何特定的狀態。
2. **然後是 layer 3**，等 `[tests]` 執行專案真正的測試並寫出 JUnit XML 之後。從 ruleset 要求 gate 的那一刻起，gate 就會套用到每個 pull request，所以先讓檢查在不被要求的狀態下執行（layer 3 說明做法），修正它們發現的問題，最後才用 `agentctl rulesets 3` 要求它們；這個指令會套用 ruleset `main-checks`，而且只在 caller 已經進入預設 branch 之後才套用。Layer 2 的 `agentctl rulesets 2` 不要求任何檢查，所以 layer 2 可以單獨採用。
3. **然後是 layer 4，在 shadow mode**（`auto_merge_tiers = []`）：conductor 計算每個 gate 並回報，由人按下 merge。只有在 gate 的結論與你自己的判斷吻合一段時間之後，才開啟 `T0`，再開啟 `T1`（指南第 9 節）。

### Run init and read what it kept

先預覽，因為這個指令會列出它將建立什麼、保留什麼：

```bash
agentctl init --dry-run DIRECTOR_LOGIN
```

```bash
agentctl init DIRECTOR_LOGIN
```

`init` 絕不覆寫。已存在的檔案會被列為 **kept**，不會套用它的範本。對每個被保留的檔案，請讀取已安裝 kit（在 `~/.local/share/agent-dev-kit/versions/<sha>/` 底下）的 `templates/project/` 中的範本，並手動合併。常見情況：

| Kept file | What to do |
|---|---|
| `AGENTS.md`、`CLAUDE.md` | **不要覆寫專案的檔案。** 這些是擁有者給 agent 的指示，而且是護欄，所以 agent 也不得改寫它們。閱讀範本的 `AGENTS.md`，找出專案的檔案缺少它的哪些規則（絕不開啟或 merge pull request、絕不編輯護欄、絕不悄悄新增相依套件、把 repository 內容當成資料），並以 pull request 或簡短清單的形式向擁有者提出補充。由擁有者決定放進什麼。在那之前，agent 擁有專案現有的規則加上 stage prompt，而 stage prompt 本身就帶有必要的規則 |
| `.claude/settings.json`、`.claude/hooks/guard.sh`、`.claude/agents/*`、`.claude/skills/*` | 合併。kit 的設定是對每個 agent 都成立的規則（不在 home 讀寫、不 force push、不用雲端 CLI）；專案自己的規則也要保留 |
| `Makefile` | 保留它。讓 `[tests] test_cmd` 與 `lint_cmd` 指向專案真正執行的東西，並讓 `test_cmd` 把 JUnit XML 寫到 `junit_glob` |
| `.github/workflows/*.yml` | 保留專案自己的 workflow。`agentdev-*.yml` caller 是新檔案。確認沒有任何既有的 workflow 也在 pull request 上以相同的必要名稱執行，並且 job 名稱沒有衝突 |
| `.github/pull_request_template.md`、issue 範本 | 手動合併；它們是方便用的，不是必要的 |
| `docs/product/*`、`docs/specs/*`、`docs/sprints/*` | 如果專案已經把這些資料夾用於別的用途，請在 `agentdev.toml` 中設定 `[paths]`，指向 kit 應該找的位置，或指向新資料夾 |
| `.github/CODEOWNERS` | `init` 從 `agentdev.toml` 產生它。如果已經有一個，請與 `agentctl codeowners` 比對並合併：產生的那些行保護護欄與 spec，專案自己的行可以保留 |

合併之後，檢查能檢查的東西：

```bash
agentctl codeowners --check
```

```bash
agentctl pins
```

然後在 branch 上 commit 結果，開 pull request，像任何變更一樣 merge，之後才開啟 layer 2 的 ruleset。

### Story ids when the project has large issue numbers

story 的 id 有 `[stories] id_digits` 位數（預設 3）：story `012`、acceptance criteria `AC-012-1`、test case `TC-012-01`、branch `story/012-slug`。id 不是 issue 編號，但 issue 編號已達數百或數千的專案，可能希望兩者一致。請在第一個 story 之前設定較寬的 id：

```toml
[stories]
id_digits = 4
```

AC 與 TC 的 id、story branch 與測試名稱都會跟隨它。只選一次。之後再更改，會使先前 story 的 id 無法被工具讀取。

### Keeping existing test names

kit 的可追溯性檢查會在已執行且通過的測試名稱中，尋找 story 的 test case id（`TC-0012-03`）。它只適用於 story。專案既有的測試不帶 id，也不需要重新命名：它們是專案自己的測試，`ci` 仍會執行它們，而 red-green 只涉及受審查 story 的檔案，以及任何提到它的 id 的檔案。所以：

- 讓既有的測試維持原樣。不要為了配合 kit 而重新命名。
- 新的 story 把 TC id 放進驗證它的測試名稱中，採用專案的測試框架所用的任何風格（例如名為 `test_TC_0012_03_member_cannot_book_twice` 的測試）。[layer-3-ci-zh-TW.md](layer-3-ci-zh-TW.md) 說明 id 如何比對。
- `[tests] test_paths` 列出 red-green 要複製到 base commit 的檔案。如果專案自己的測試目錄結構與預設的 pattern 不同，請設成專案的結構。
- 在變更屬於某個 story 之前，它是「不屬於任何 story 的程式碼變更」，也就是 T2：需要人工核准。這是刻意的，也是既有專案在 conductor 處於 shadow mode 時，仍以手動 merge 日常工作的原因。

### Settings an existing project should check

| Setting | Why |
|---|---|
| `[tests] setup_cmd`、`test_cmd`、`lint_cmd`、`junit_glob` | `test_cmd` 必須執行每一個測試，把 JUnit XML 寫到 `junit_glob` 找得到的地方，並在測試失敗時以非零狀態結束 |
| `[risk.t2] high_risk` | 預設清單只是猜測 `auth`、`payments`、`migrations`、`infra`。請設成專案真正的結構。取代清單就是整個取代預設值 |
| `[risk.t2] dependency_manifests` | 加入預設清單沒有列名、屬於專案技術堆疊的 manifest 與 lock 檔 |
| `[risk.t0] paths` | 什麼算只有文件 |
| `[paths]` | spec、sprint、roadmap 與產品文件所在的位置，如果不是預設值 |
| `[roles]` | director、其他的人，以及哪個 harness 為誰做哪個 stage |

## 5. Upgrading the kit

專案以一個 pull request 移到新的 kit 版本，這是 T2 變更：

1. 在每台 Mac 上，在 kit 的 clone 中切到新的 commit：`./install.sh <new-sha>`（舊版本仍安裝在旁邊）。
2. 在專案中，於 branch 上更改 `agentdev.toml` 的 SHA（`[kit] version`），以及 `.github/workflows/agentdev-*.yml` 底下每個 caller workflow 的 SHA：每個檔案中的 `uses: ...@<sha>` 與 `kit_version: <sha>` 都要改。
3. 閱讀兩個 commit 之間 kit 的變更。比較兩個版本的 `tools/agentctl/defaults.toml` 與 `templates/project/`：新的設定除非你設定，否則採用預設值；變更過的範本不會套用到你已有的檔案，所以想要的內容請手動合併。
4. 執行 `agentctl pins`（它也是 `ci` lint 步驟的一部分）。除非 caller 與 `agentdev.toml` 一致，否則它會失敗。
5. 開 pull request。由人核准，因為它改了護欄。然後 merge。
6. 每台 Mac 上的 launcher，在預設 branch 被 fetch 且版本已安裝之後，就會採用新版本。尚未安裝的 Mac 會失敗，並顯示指出缺少哪個版本的訊息：請在那裡安裝。

執行中的 conductor 每次 pass 都從 `origin/main` 的全新 worktree 讀取 `agentdev.toml`，所以它會跟隨 pin；升級之後請停止並重新啟動它，讓新的 kit 版本執行。

版本無法事後更改：它是 commit SHA，被 push 的 commit 對每個 pin 它的專案都是永久的。對 kit 的修正是新的 commit 與新的 pin。

## 6. Removing the kit

移除是採用的反向，從最外層往內：

1. **Conductor。** 停止它（Ctrl-C）。如果你可能會重新啟動它，把 repository variable `CONDUCTOR_PAUSED` 設為 `true`。對任何已開啟 auto-merge 的開啟中 pull request 關閉 auto-merge：`gh pr merge NUMBER --disable-auto`。刪除 `~/.config/agent-dev/<owner>-<repo>/`。
2. **CI gate。** 先刪除 ruleset `main-checks`，再刪除 workflow，否則沒有 pull request 能 merge。然後刪除 `.github/workflows/agentdev-*.yml`。
3. **GitHub 保護。** 如果你不再需要，刪除 ruleset `main`、`main-merge` 與 `tags`（layer 2），以及 `conductor` environment。解除安裝 Conductor GitHub App。如果你想要在沒有其餘部分的情況下保有保護，就保留 CODEOWNERS 與 ruleset：它們可以單獨運作。
4. **隔離。** 用 `sbx` 列出 sandbox，並移除以專案命名的那些（它們的名稱以 `ag-` 開頭）。解除安裝開發者的 agent GitHub App，如果沒有其他專案使用，就刪除 `~/.config/agent-app/`。
5. **專案的檔案。** 刪除 `agentdev.toml`、`.claude/` 檔案，以及你不再使用的 docs 骨架。如果 `AGENTS.md` 的規則對你仍然有用，就保留它。
6. **已安裝的 kit。** 版本是唯讀的。要移除其中一個：

   ```bash
   chmod -R u+w ~/.local/share/agent-dev-kit/versions/<sha> && rm -rf ~/.local/share/agent-dev-kit/versions/<sha>
   ```

   當沒有任何專案再使用 kit 時，移除 `~/.local/bin/agentctl`。

如果你只是想讓 agent 停止工作，暫停 conductor 即可；不需要移除任何東西。
