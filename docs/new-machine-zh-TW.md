# 設定一個人與他的電腦

*English: [new-machine.md](new-machine.md)。兩份內容不一致時以英文版為準。*

每位名下會有 story 交給 agent 的人各自執行。第 2、3、5 節是每個人在每個專案做一次；第 4 節是每台電腦做一次，換新電腦時重做。

前提是專案已經建立：[new-project-zh-TW.md](new-project-zh-TW.md) 的第 1 到第 5 節已經做完。也就是說，repo 已經存在而且 `main` 上是 template 的內容，Conductor App 已經安裝，`conductor` environment 已經建立並帶有它的 branch rule，ruleset 也已經套用。如果你就是設定專案的人，先做完那五節再回來。

這份文件裡的每個指令，都在你的專案 clone 裡、在 default branch 上執行。如果你還沒有 clone，就在不受 iCloud 同步的位置建立一個：

```bash
mkdir -p ~/dev && cd ~/dev && gh repo clone OWNER/REPO && cd REPO
```

標示 **待驗證** 的地方還沒在真實的帳號或機器上跑過。做的時候請對照當下的官方文件，並把結果回寫到這份文件。

## 1. 需要什麼

- 每位名下會有 story 交給 agent 的人，至少一種 AI coding 訂閱，例如 Claude Max 或 ChatGPT。不需要 API key。
- Mac 上：Python 3.11 或更新的版本。工具使用 `tomllib`，並以 `python3 -I` 啟動。用這個指令確認：

```bash
python3 --version
```

- Mac 上：Docker Sandboxes（`sbx`）。只有使用備援 VM 時才需要 Homebrew 與 Lima。
- 夠新的 `gh`，只有在你要在這台 Mac 上跑本機 conductor（`agentctl conductor here`）時才需要。Conductor 會用到 `gh variable get` 與 `gh variable set`，較舊的版本沒有這兩個指令。目前不知道確切的最低版本。用這個指令確認：

```bash
gh variable get --help
```

## 2. Agent GitHub App

每位開發者為自己的 agent 建立一個 GitHub App，這樣 commit 與留言就看得出是誰的 agent 做的。在你個人帳號的 Settings > Developer settings > GitHub Apps：

- 以自己命名，例如 `yourname-agent`。
- Repository permissions：Contents: Read and write；Pull requests: Read and write；Issues: Read and write；Metadata: Read。其他都不要，尤其**不要** Workflows、Administration、Commit statuses、Secrets、Variables。
- 不訂閱任何 webhook，取消勾選 Active。
- 建立後產生一把 private key，並把 App 只安裝到這個 repo。

這份清單是 App 最多能做的事。沒有任何一個 sandbox 會拿到全部。Mac 上的 helper 為每個 sandbox 簽發一個一小時的 token，權限只是 App 權限的一部分。每個 stage 拿到哪一部分，固定寫在 `tools/agentctl/profiles.py`：

| Token | Stage | Contents | Pull requests | Issues |
|---|---|---|---|---|
| `write` | design、tests、impl、fix、resolve-conflict、fix-main、product-owner、planner | write | read | write |
| `read` | review、triage，以及該檔案沒有列出的任何 stage | read | write | write |

所以能 push 的 token 不能開 pull request，也不能 review；能 review 的 token 不能 push。Merge 是另一回事。GitHub 的 merge endpoint 只要求 Contents: write，而 `write` token 有這個權限，所以擋住 agent merge 的不是 token，而是 `main-merge` ruleset：只有 repo admin 與 Conductor App 可以更新 default branch。App 本身需要 Pull requests: Read and write，是因為 review stage 的 token 要寫入 pull request；需要 Contents: Read and write，是因為建置類 stage 的 token 要 push。開 pull request 與 merge 是 conductor 的工作。**待驗證**：GitHub 確實會簽發這樣縮小權限的 installation token；`write` token 嘗試開 pull request 時會被拒絕；而且 `main-merge` ruleset 會拒絕它 merge 一個其他條件都已就緒的 pull request（[redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) 的 C17）。

留下 App 的 ID 與 private key 檔。第 4 節會把它們放在你的 Mac 上、sandbox 之外。**待驗證**：`agentctl app-token` 還沒對真實 API 執行過。

要以留言啟動雲端任務，每位開發者另外需要一個個人 token `DISPATCH_TOKEN`：只限這個 repo 的 fine-grained personal access token，權限為 Issues: Read and write；Pull requests: Read and write；Metadata: Read。它出自開發者本人的帳號，因為留言者可能必須是連結了 ChatGPT 帳號的使用者（**待驗證**）。

## 3. 你的 secrets

這些屬於你自己的訂閱。請把它們建立為 `conductor` environment 的 **environment secret**，這個 environment 已在 [new-project-zh-TW.md](new-project-zh-TW.md) 建立：repo 的 Settings > Environments > `conductor` > Environment secrets。不要把它們建立成 Secrets and variables > Actions 底下的 repository secret。這個 environment 的 deployment branch rule 只允許 default branch，所以從其他 ref 執行的 workflow 拿不到這些 secret。Repository secret 沒有這種限制（**待驗證**：Team 方案的 private repo 上，帶 deployment branch rule 的 environment）。

| 類型 | 名稱 | 來源 | 何時需要 |
|---|---|---|---|
| Environment secret | `DISPATCH_TOKEN` | 第 2 節 | Codex 以留言啟動時 |
| Environment secret | `CLAUDE_CODE_OAUTH_TOKEN` | 在你的機器上執行 `claude setup-token` | Claude review |
| Environment secret | `CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN` | 第 5 節建立的 scheduled task | Claude 雲端 session |

Claude review 只需要你建立 `CLAUDE_CODE_OAUTH_TOKEN` 這一個憑證。在 GitHub 上，review job 用的是 Actions 發給該 job 的 token。

要用哪個名稱存放它們，取決於 sprint 檔怎麼分配 story：

- Sprint 檔沒有交給特定人的 story（`assignee = "default"`，而且 `[owners]` 裡沒有它的項目）使用不帶後綴的名稱：`DISPATCH_TOKEN`。
- Sprint 檔交給指名的人的 story 只使用那個人的名稱：在不帶後綴的名稱後面加上大寫的帳號，其他字元換成 `_`，例如 `DISPATCH_TOKEN_ALICE` 或 `CLAUDE_TRIGGER_URL_ALICE_SMITH`。如果那個 secret 不存在，派發會失敗並說明原因。它不會退回去用不帶後綴的名稱，因為那樣會在沒有人察覺的情況下，用另一個人的訂閱去跑某個人的 story。

只有一個人時，可以保留 `assignee = "default"` 並使用不帶後綴的名稱，也可以在 sprint 檔裡指名自己並使用後綴。有好幾個人時，讓每個人都用帶後綴的 secret，並為每個 story 指名 owner。

## 4. Mac 與 sandbox

```bash
bin/agentctl doctor
```

修掉所有 FAIL。本機 sandbox 用的是 clone 模式的 Docker Sandboxes。依其文件安裝 `sbx`（docs.docker.com/ai/sandboxes），然後登入：

```bash
sbx login
```

把你的 agent App 的 ID 與 private key（第 2 節）放在 Mac 上。它們留在 host，sandbox 內的任何東西都讀不到。把 `APP_ID` 換成你的 App ID，檔名換成你下載的 key 檔：

```bash
mkdir -p ~/.config/agent-app && echo APP_ID > ~/.config/agent-app/app-id
```

```bash
mv ~/Downloads/YOUR_APP.private-key.pem ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

每次使用 `sandbox/sbx.sh` 都要遵守兩條規則。

**只從 default branch 的乾淨 checkout 執行它。** 絕對不要在你切出來的 agent branch 上執行。這支 script 在 Mac 上以你的權限執行。如果目前切在 agent 的 branch 上，你執行的那份 script 就是 agent 寫的。為了防止這種意外，`setup`、`up`、`job` 在 `sandbox/`、`tools/`、`bin/` 或 `policy/` 與 default branch（以你的 clone 上次 fetch 到的為準）不同時會拒絕執行；`sandbox/`、`tools/`、`bin/` 內有未追蹤的檔案時也一樣。`bin/agentctl conductor here` 有相同的檢查。這項檢查本身就是那些 script 的一部分，所以它保護不了一個已經被動過手腳的 checkout。這條規則要靠你自己遵守：留一個永遠停在 default branch 的 checkout，host 上的指令只從那裡執行。`AGENT_ALLOW_MODIFIED_SCRIPTS=1` 會關掉這項檢查，它是給開發這些 script 本身時用的。

**專案目錄內不可以放任何機密，被 git 忽略的檔案也算。** Clone 模式會把整個目錄以唯讀方式掛進每個 sandbox，位置是 `/run/sandbox/source`。這包含 git 忽略的檔案，例如 `.env` 檔，也包含 git 單純沒有追蹤的檔案。只要找到檔名像機密的未追蹤檔案，不論是否被忽略，script 就拒絕設定機器、建立 sandbox 或重新接上既有的 sandbox。這些檔名是：`.env*`、`*.pem`、`*.key`、`*.p12`、`*.pfx`、`id_rsa*`、`id_ed25519*`、`id_ecdsa*`、`credentials*`、`.netrc`、`.npmrc`、`.pypirc`，以及任何含有 `secret` 的名稱，不分大小寫。它會列出這些檔案然後停止。請把它們移出 repo。這項檢查只看檔名，換個名字的機密就找不到，不要依賴它。`AGENT_ALLOW_FILES_IN_TREE=1` 可以讓 script 照樣繼續。本機 conductor 自己的憑證也因為這個原因放在 repo 之外：`~/.config/agent-dev/OWNER-REPO/conductor.env`（[operations-zh-TW.md](operations-zh-TW.md) 第 1 節）。

接著：

```bash
sandbox/sbx.sh setup
```

Setup 依序做以下的事：

1. 關掉 SSH agent forwarding（`sbx settings set ssh.agentForwardingEnabled false`）與共用的 skills store（`sbx settings set skills.defaultMode off`）。兩者都是整台機器的 sbx 設定：對你所有的 sandbox 生效，不只是這個專案的。
2. 要求 deny-all 的網路 preset（`sbx policy init deny-all`）。Allowlist 只有疊在 deny-all 之上才有意義。
3. 重新啟動 sbx daemon。
4. 把固定版本的工具與兩個 token helper 安裝在 repo 之外（見下文）。
5. 對所有 sandbox 放行 `sandbox/allowlist.txt` 所列的主機：原始碼管理與模型供應商。套件 registry 不在這份清單裡。

如果 sbx 已經有網路 preset，第 2 步會失敗，setup 會停止。Docker 的「balanced」preset 就是一例，它放行套件管理工具。sbx 無法就地更換 preset，所以 setup 會要求你改用這個方式重新執行：

```bash
AGENT_RESET_POLICY=1 sandbox/sbx.sh setup
```

帶 `AGENT_RESET_POLICY=1` 時，setup 會先執行 `sbx policy reset --force`。**這會移除這台機器上所有既有的 sbx 網路規則**，包含你為與這個專案無關的 sandbox 設定的規則。然後它從 deny-all 重新開始。執行前先記下你還需要的規則。**待驗證**：在已經是 deny-all 的機器上再執行一次 `setup`，是否也會停在第 2 步。如果會，之後每次執行 `setup` 都需要 `AGENT_RESET_POLICY=1`，而當時存在的 sandbox 會失去它們自己的規則；請移除它們再重新啟動。

固定版本的工具放在 `~/.local/share/agent-dev/OWNER-REPO/`（有設定 `$XDG_DATA_HOME` 時在它底下），其中 `OWNER-REPO` 取自 origin remote。不同 repo 的兩個 clone 不會共用它。裡面有一份 `tools/agentctl` 與 `tools/run.py`，內容取自 origin 上的 default branch，不是你的 working tree；另外有兩個 helper：`github-token-write` 與 `github-token-read`。Sandbox 需要 GitHub token 時，host 上的 sbx proxy 會執行其中一個。這個目錄裡的東西一律以 `python3 -I` 啟動，所以目前目錄中的檔案無法冒充它。拉下工具的更新之後，要再執行一次 `sandbox/sbx.sh setup` 來更新這份固定的副本。

若要讓 sandbox 能連到 Mac 上的 Ollama，setup 改用這個方式執行：

```bash
AGENT_OLLAMA=1 sandbox/sbx.sh setup
```

依 sbx 文件對各 harness 的說明登入。撰寫本文時，Codex 是在 host 上執行 `sbx secret set openai --oauth`，Claude Code 是在 sandbox 內執行 `/login`（**待驗證**，包含這樣登入之後，之後才建立的 sandbox 是否也能使用；無人看管的 job 需要這一點）。

啟動一個互動式的 agent，然後在第二個 terminal 檢查邊界：

```bash
sandbox/sbx.sh up claude
```

```bash
sandbox/sbx.sh check claude impl
```

互動式的 sandbox 是每個 stage 一個。`up` 的第二個參數指定 stage，預設是 `impl`。Stage 決定 sandbox 拿到的 token、網路與 deny rules，依據是固定副本裡的 `profiles.py`。Sandbox 的名稱是 `agent-OWNER-REPO-STAGE-HARNESS`，所以 `up claude` 與 `up claude review` 是兩個不同的 sandbox。Review 的那一個拿到不能 push 的 token，也連不到套件 registry：

```bash
sandbox/sbx.sh up claude review
```

`check` 與 `rm` 接受同樣的兩個參數，先 harness 後 stage，預設是 `claude` 與 `impl`：

```bash
sandbox/sbx.sh check claude review
```

```bash
sandbox/sbx.sh rm claude review
```

對同一個 harness 與 stage 再執行一次 `up`，會重新接上那個 sandbox。它會一直留著，直到你用 `rm` 移除。需要建置的 stage（design、tests、impl 與各個 fix stage）另外會拿到 `sandbox/allowlist-build.txt` 所列的主機，只對該 sandbox 生效。

無人看管的 job 不一樣。本機 conductor 以 `sandbox/sbx.sh job` 啟動每一個 job，使用的是它自己的 default branch checkout。每個 job 都拿到一個全新的 sandbox，名稱以時間戳結尾、不會重複；job 結束後不論結果如何，sandbox 都會被移除。如果同名的 sandbox 已經存在，job 會拒絕執行。Log 留在 Mac 上的 `~/.local/state/agent-dev/OWNER-REPO/`。本機 sandbox 只會在 story 所屬開發者的 Mac 上啟動，也就是 `conductor.env` 裡 `DEVELOPER` 那一行所指的人。

Agent 在自己的 clone 上工作，以 push 交付成果。想在它 push 之前看它的工作，可以從 sbx 加到你 repo 的 remote 取得。先列出 remote 找到它的名稱；預設的互動式 sandbox 應該是 `sandbox-agent-OWNER-REPO-impl-claude`（**待驗證**）：

```bash
git remote
```

```bash
git fetch sandbox-agent-OWNER-REPO-impl-claude
```

Fetch 是安全的。不要在你用來執行 host script 的那個 checkout 裡切到那個 branch。

**待驗證**（實機）：這一節的全部內容。sbx 的指令是依 2026 年 11 月讀到的 Docker Sandboxes 文件寫的，還沒有執行過。特別要確認 sandbox 內的 `git push` 會成功，而且歸屬於你的 agent App，並把結果記在 [redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) 的 C11。

備援：Lima。只有在你無法使用 sbx 時才用，而且只用於互動式的工作。它較弱，你應該知道弱在哪裡：

- Workspace 是可讀寫掛載，所以 agent 可以改動 Mac 上的檔案，包含 `.git/hooks`，以及 VM 自己會執行的、位於 `/workspace` 底下的工具。這裡沒有固定的副本。
- 連線以位址過濾，不是以主機名稱過濾。
- App 的 key 必須放在 VM 內。
- 一個長期存在的 VM 服務所有的 stage。它拿到最寬的 allowlist（兩份檔案都算）與一個 `write` profile 的 token。沒有任何東西按 stage 縮小，session 之間也不會清掉任何東西。

這個 VM 的 self-hosted runner（`sandbox/runner/`、`agent-job.yml`），以及在 Actions 額度快用完時把 CI 移到它上面，都**不屬於受支援的設定路徑**。`ci` 與 `security` 會執行 pull request 的程式碼，而這個 VM 長期存在、有免密碼的 sudo，還保存著你的 agent 的登入狀態。預算 overflow 預設是關閉的（`policy/conductor.toml` 的 `overflow_runner = []`）。理由與已知的缺口寫在 [sandbox/runner/README-zh-TW.md](../sandbox/runner/README-zh-TW.md)。在受支援的設定中，沒有任何東西會把工作派給這個 VM；你要自己手動在裡面啟動 agent。

```bash
brew install lima
```

```bash
sandbox/vm.sh up
```

```bash
sandbox/vm.sh check
```

```bash
sandbox/vm.sh shell
```

以下在 VM 內執行。先登入你的 harness（`claude`、`codex login`），再把 agent App 的 key 交給 VM：

```bash
mkdir -p ~/.config/agent-app && cat > ~/.config/agent-app/key.pem && chmod 600 ~/.config/agent-app/key.pem
```

貼上 private key 後按 Ctrl-D。接著，把 `APP_ID` 換成你的 App ID、`yourname-agent` 換成你的 App 名稱：

```bash
echo 'export AGENT_APP_ID=APP_ID AGENT_APP_KEY=$HOME/.config/agent-app/key.pem PATH=/workspace/sandbox/bin:$PATH' >> ~/.profile && . ~/.profile
```

```bash
git config --global credential.https://github.com.helper '!/workspace/bin/agentctl app-token --git-credential' && git config --global user.name "yourname-agent[bot]" && git config --global user.email "yourname-agent[bot]@users.noreply.github.com"
```

```bash
mkdir -p ~/.claude && cp /workspace/sandbox/story-agent.claude-settings.json ~/.claude/settings.json
```

最後一個指令安裝的是 story agent 專用的 deny rules。另外把 `codex/config.example.toml` 的 `vm` profile 複製到 `~/.codex/config.toml`。雲端環境也要套用同一組 story agent 規則（**待驗證**：兩家雲端服務設定使用者層規則的方式）。

## 5. 雲端 agent

### Claude Code on the web

1. 在 claude.ai/code 以你自己的帳號連結 GitHub，只授權這個 repo。雲端 agent 之後在 GitHub 上是以你的身分操作。[redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) 的 E 節檢查它用這個身分能做到什麼；讓雲端 session 無人看管地工作之前先跑過那一節。
2. 建立一個環境：網路設為受限，不加任何 secret。
3. 建立一個 scheduled task，觸發方式選 API，prompt 設為「執行收到的訊息中的指示」。把它的觸發 URL 與 token 存成 environment secret `CLAUDE_TRIGGER_URL`、`CLAUDE_TRIGGER_TOKEN`（第 3 節）。

**待驗證**：API trigger 的請求格式。`tools/agentctl/github.py` 的 `_send` 目前假設是帶 Bearer token 的 POST，body 為 `{"text": "..."}`。依實際文件調整這一個函式即可。

PO chat：在 Claude app 開一個掛著這個 repo 的 Claude Code session，輸入 `/po` 後說出需求。

### Codex cloud

1. 在 chatgpt.com/codex 連結 GitHub 並授權這個 repo。
2. 建立環境：agent 階段的網路關閉或設為 allowlist，不加 secret。
3. 開啟 automatic reviews。Review 規則讀 `AGENTS.md` 的 Code Review Rules 一節。

**待驗證**：在 PR 或 issue 上留 `@codex <指示>` 是否會啟動任意任務；review 的結果是以 PR review 還是留言呈現，`agent-review` workflow 的 `bridge` job 要對應調整。

## 6. Red-team

在這台電腦上執行 [redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) 的全部項目。大多數項目預期的是失敗或被拒絕；少數預期成功的項目列在 checklist 的開頭說明裡。任何一項的結果與預期不同，就先修好再讓 agent 無人看管地工作。

## 7. Ollama（之後再做）

Ollama 裝在 Mac 上（需要 GPU）。以 `AGENT_OLLAMA=1 sandbox/sbx.sh setup` 放行該 port 之後，sandbox 可經 `host.docker.internal:11434` 存取它（**待驗證**：setup 在 sbx policy 中放行的是 `localhost:11434`；要確認這就是 sandbox 所用位址需要的規則）。在 Lima 備援中，`sandbox/egress.sh` 已經透過 host gateway 放行。

- 24GB 記憶體的 M2：選 14 到 15GB 級的模型（例如 devstral 24b、gpt-oss 20b）。19GB 級的模型加上大 context 會很吃緊。模型名稱與大小請以當下的 Ollama 模型庫為準。
- 一定要調高 context window。預設值很小，agent 會靜默遺失開頭的指示。
- 定位在 T0 類的工作：文件、lint 修正、測試骨架。產出一樣要過所有 gate。
- 在 `policy/roles.toml` 把想交給它的 stage 加上 `"ollama"`。Ollama 的 stage 在本機的 Docker Sandbox 內執行（`via = "sbx"`），由本機 conductor 以 `sandbox/sbx.sh job` 啟動。它們不在 self-hosted runner 上執行。所以這些 stage 只有在 conductor 跑在你的 Mac 上（`agentctl conductor here`）時才會開始。屬於另一位開發者的 story 會等那位開發者的 Mac。
- 模型由本機 conductor 的環境變數 `OLLAMA_MODEL` 決定，預設是 `devstral`。
