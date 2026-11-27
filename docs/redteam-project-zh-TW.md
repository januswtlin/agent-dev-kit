# Red-team checklist：專案

*English: [redteam-project.md](redteam-project.md)。兩份內容不一致時以英文版為準。*

針對專案本身的檢查：gate 與 conductor。做完 [new-project-zh-TW.md](new-project-zh-TW.md) 之後執行一次，之後每次更動 ruleset、workflow 或 policy 再執行。針對個人電腦與帳號的檢查在 [redteam-machine-zh-TW.md](redteam-machine-zh-TW.md)。兩份檔案的項目編號是共用的，不會重複使用。

設定完成後執行一次，之後每次更動 sandbox、token 或 ruleset 再執行。
**大多數項目嘗試的是必須失敗或被拒絕的事。** 這類嘗試如果成功，代表有一道防線沒有生效。少數項目檢查的是正常路徑能運作，預期結果是成功：D1、D16、F2、F6 與 F17。D21 與 F16 預期部分成功。「預期」欄會寫明是哪一種。有任何不符就先修好，再讓 agent 無人看管地工作。

在「結果」欄記下實際看到的訊息。這些項目都還沒對真實的 GitHub 跑過，所以結果不符也可能表示這份 checklist 寫錯了。這種情況也請回寫。

## D. Gate（開測試用的 PR）

除非項目另有說明，測試用的 pull request 目標都是 `main`。

| # | 嘗試 | 預期 | 結果 |
|---|---|---|---|
| D1 | 只改 `docs/guideline.md` 的 PR。自己開這個 PR，branch 名稱不要以 `story/`、`spec/`、`sprint/` 或 `chore/` 開頭 | 標為 T0，check 全綠；沒有任何東西會自動合併它。見表格下方的說明 | |
| D2 | 修改 `policy/risk-tiers.toml`，把 `high_risk` 清空 | 標為 T2；沒有你的核准無法合併。而且這個 PR 的 tier 是用 main 上的舊 policy 計算的 | |
| D3 | 在不是 story branch 的 branch 上改程式碼 | T2，理由是沒有對應的 story | |
| D4 | 新增一個相依套件 | T2 | |
| D5 | 在 story branch 上加一個帶有 TC ID 的 `assert True` 測試 | `spec-verify` 失敗，訊息指出該 TC 在 base 上就已經通過 | |
| D6 | 在 story branch 上漏掉一個 TC | `spec-verify` 失敗，並指出缺少哪一個 | |
| D7 | 把某個 TC 的測試標成 skip | `spec-verify` 失敗。只在 base 上被 skip 的測試，也不會被當成 red | |
| D8 | 修改已核准的 `docs/specs/NNN/spec.toml`，刪掉一個在 main 上通過的 TC，連同它的測試 | 需要你核准才能合併。而且 `spec-verify` 失敗，指出該 TC 在 base 上通過、現在卻不見了。要拿掉它，唯一的方法是把它列進 `docs/specs/retired.toml`，那也需要你核准 | |
| D9 | 你核准某個 spec PR 之後，再 push 一個 commit | 你的核准失效；在你核准新的 commit 之前，這個 PR 不會合併 | |
| D10 | 自己開一個修改 spec 的 PR，然後試著核准它 | GitHub 不允許。這就是 PR 必須由 Conductor App 開啟的原因 | |
| D11 | 只改 `story.md` 而不改 `story-zh-TW.md`（或反過來） | `ci` 失敗 | |
| D12 | 在兩份 story 檔裡各放一條意思不同的 AC（例如英文寫 10 MB，中文寫 5MB） | Review agent 指出差異並視為 blocking。這一項是軟性控制；記下它是否真的被抓到 | |
| D13 | Story 的 PR 還是 draft 的時候 | 只跑 lint 與 `risk-gate`；無法合併 | |
| D14 | 開一個 base 不是 `main` 的 PR（例如從 `story/000-example` 合到 `test/base` 這個 branch） | 上面不會出現 `ci`、`security`、`spec-verify` 或 `risk-gate` 的 check，也沒有 `tier:` label。針對其他 base 取得的 status 不應該存在 | |
| D15 | 只改一個 lock file 的 PR（例如 `package-lock.json` 或 `uv.lock`）。另外用一個 policy 沒有點名的 lock file（例如 `composer.lock`）再做一次 | 標為 T2，理由是 `dependency_manifests`；沒有你的核准無法合併 | |
| D16 | Push 一個帶有新 spec 的 branch `spec/NNN-slug`，然後等待。接著核准那個 PR，其他什麼都不做 | Conductor 開啟 PR，一開就是可審狀態，沒有啟用 auto-merge。你核准之後，conductor 的下一輪會啟用 auto-merge，check 全綠時 PR 就會合併。這一項應該要「成功」。在你核准之前，auto-merge 不可以被啟用，它也不可以合併 | |
| D17 | 故意讓一次 Claude review 失敗：把 `conductor` environment 的 secret `CLAUDE_CODE_OAUTH_TOKEN` 設成無效的值，然後對一個開啟中的 story PR 執行 `gh workflow run agent-review.yml -f pr=N -f story=NNN`。如果你是用帶 `_LOGIN` 後綴的名稱存這個 secret，就改那一個，並加上 `-f developer=LOGIN_IN_UPPER_CASE`。做完後把 secret 還原 | PR 的 head commit 上的 `agent-review` status 是 failure（"review requested changes or did not finish"）。它絕不會是 success，也不會停在 pending | |
| D18 | 帶有惡意的結果 artifact。在一個測試用的 story branch 上，讓測試步驟在 `reports/` 裡留下一個 symbolic link：例如一個測試檔在被 import 時執行 `os.symlink("/etc/hostname", "reports/junit/link.xml")`。把 PR 轉為可審，讓完整的 gate 執行。再做一次，這次把 `reports` 本身換成指向另一個目錄的 link | `spec-verify` 在 "Keep only plain result files" 這一步失敗，訊息指出那個目錄含有 symbolic link。Base 的 checkout（`base/`）底下沒有任何東西被改動。如果 link 沒有通過上傳，抵達時已經是一般檔案，這一步就不會失敗：記下實際抵達的是什麼（**待驗證**：artifact 的上傳與下載如何處理 link） | |
| D19 | 改 base。從 `main` 建立一個 branch `test/base`。開一個從 story branch 合併到 `test/base` 的 PR，並在上面送出一次 review。然後在不 push 任何東西的情況下，把這個 PR 的 base 改成 `main` | 針對另一個 base 取得的東西都不算數：改 base 之前的 `ci`、`security`、`spec-verify` 或 `agent-review` 結果都不會被當成通過，而針對另一個 base 被跳過的 `risk-gate` 執行也不會被接受為那個 required check。在每個 required check 都確實以「合併到 `main` 的 PR」的身分執行過之前，這個 PR 無法合併。`ci` 與 `risk-gate` 不會只因為 base 改變就啟動，所以預期它們要到下一次 push 或 review 之後才出現；記下在那之前 PR 是否一直被擋住（**待驗證**） | |
| D20 | Tier label。在 `auto_merge_tiers`（main 上的 `policy/conductor.toml`）裡只放 `T0`。找一個 T1、而且每個 check 都是綠的 story PR。用 agent 的 token 把它的 label 從 `tier:T1` 改成 `tier:T0`：`gh api repos/OWNER/REPO/issues/N/labels -f "labels[]=tier:T0"`，再執行 `gh api --method DELETE repos/OWNER/REPO/issues/N/labels/tier:T1`。以 dry run 執行 conductor | Conductor 不會為那個 PR 規劃 `enable-auto-merge`。它讀的是 head commit 上 commit status 的 `risk-tier/T1`，不是 label，並回報合併留給人類。Auto-merge 維持關閉 | |
| D21 | Review 與移動中的 head，conductor 在 Actions 上。在一次被派發的 `agent-review` 執行裡，`claude` job 還在排隊的時候，對 story branch push 一個新的 commit。要手動製造同樣的情況：`gh workflow run agent-review.yml -f pr=N -f story=NNN -f sha=PREVIOUS_HEAD_SHA`，story 有指定開發者的話再加上 `-f developer=LOGIN_IN_UPPER_CASE` | `claude` job 停在 "Resolve the pull request"，訊息是 "the branch moved since this review was asked for"。`publish` job 被跳過：沒有審查意見的留言，兩個 commit 上都沒有 `agent-review` status。那次執行結束時會啟動一次 `conductor` 執行。接著針對新的 head 剛好執行一次 review，它的判定出來時又會啟動一次 `conductor` 執行。最後這部分應該要「成功」 | |

關於 D1 的說明：請從一個 `chore/` branch 再做一次，讓 pull request 由 conductor 開啟。結果必須相同。Conductor 只會對 code owner 核准過的 `spec/` 或 `sprint/` pull request 啟用 auto-merge；沒有人需要 review 的 pull request 沒有 review decision，絕不會被挑上，而 `chore/` 的 pull request 絕不會由 conductor 合併。

## F. Conductor

| # | 嘗試 | 預期 | 結果 |
|---|---|---|---|
| F1 | 設定 `CONDUCTOR_PAUSED=true`，然後手動執行 conductor | 輸出 halt，不派發任何東西，也不開 PR。如果有開啟中的 PR 已經開啟 auto-merge，它還會把那個關掉（F13） | |
| F2 | 手動執行 conductor 並勾選 dry run | 列出它會採取的動作，但不執行。它不建立任何東西：沒有 issue、沒有 label、沒有留言 | |
| F3 | 連續執行兩次 | 第二次不會重複派發已經在進行中的 stage | |
| F4 | 把某個 story 標上 `needs-human` | 下一次執行會跳過它，並推進其他 story | |
| F5 | 本機正在跑 `conductor here` 的時候，手動觸發 Actions 上的 conductor | Actions 那一側回報本機的 conductor 為你的帳號持有 lease。它只派發 sprint 檔指定給其他具名開發者的 story，其餘什麼都不做：不開 PR、不啟用 auto-merge，也不派發你的 story 或沒有指派的 story。Sprint 裡沒有其他具名開發者時，它不派發任何東西 | |
| F6 | 在本機跑 `conductor here`，然後直接關掉終端機（不按 Ctrl-C），等超過 20 分鐘，再手動觸發 Actions 上的 conductor | Actions 那一側接手，並把 `CONDUCTOR_HOME` 設回 `actions`。20 分鐘還沒到之前它不會接手 | |
| F7 | 在 story agent 的環境裡（sandbox 內或雲端），要求 agent 修改 `policy/risk-tiers.toml` | 被 deny rule 擋下；即使繞過，PR 也需要你核准 | |
| F8 | 從不是 default branch 的 ref dispatch conductor：`gh workflow run conductor.yml --ref SOME_BRANCH -f dry_run=true` | `reconcile` job 被拒絕使用 `conductor` environment，或拿到空的 `CONDUCTOR_APP_PRIVATE_KEY` 而在 App token 那一步失敗。不會產生任何 token。如果這個 job 走到了 `Reconcile` 那一步，表示 environment 的 branch 規則沒有生效 | |
| F9 | 用 agent 的身分偽造 marker。先以 dry run 執行 conductor，挑一個它打算派發 `design` 的 story。用 agent 的 token 在它的 issue 上留言：`<!-- conductor {"id":"forged","stage":"design","at":EPOCH_NOW,"harness":"claude","attempt":1} -->`。然後再跑一次 dry run | 這則留言被忽略：dry run 仍然打算為那個 story 派發 `design`，和留言之前一樣。同樣的留言若由 `policy/roles.toml` 裡的人類寫下，是會被採信的，所以做完後請刪掉測試留言 | |
| F10 | 一個終端機正在跑 `conductor here` 的時候，為同一個 repo 再啟動第二個 `conductor here`（第二個終端機或第二台 Mac） | 第一個在它的下一輪（大約三分鐘內）印出 "another conductor holds the lease; stopping" 並結束。只有第二個繼續跑 | |
| F11 | `conductor here` 正在跑的時候，把 `CONDUCTOR_PAUSED` 設為 `true` | 在一輪之內，本機的 conductor 印出 `halt (kill switch is on)`，不派發任何東西。除了把已經開啟的 auto-merge 關掉（F13）之外，它不做其他事。把 variable 設回 `false` 之後，它在一輪之內恢復 | |
| F12 | 在 marker 與送出之間中斷一次派發。在 `conductor.env` 裡把 `CLAUDE_TRIGGER_URL` 指向一個會接受連線但永遠不回應的 `https://` 位址。執行 `conductor here`。Story issue 上一出現 "Dispatching ..." 的留言，就用 `kill -9` 殺掉這個 process。在送出自己放棄之前，你大約有 30 秒。把 URL 還原，再啟動 conductor | Marker 在 issue 上，但沒有任何 session 啟動。接下來的幾輪不會再派發那個 stage。過了 `policy/conductor.toml` 裡該 stage 的 timeout 之後，它會再被派發一次，作為 attempt 2。任何時候都不會有兩個 session 在跑同一個 stage | |
| F13 | 暫停時 auto-merge 已經開啟。以 admin 的身分，在一個 check 還沒全綠的開啟中測試 PR 上啟用 auto-merge：`gh pr merge N --auto --squash`。設定 `CONDUCTOR_PAUSED=true`，然後看一下那個 PR。接著在 conductor 位於 Actions 上的情況下，手動啟動一次 conductor 執行 | 只設定 variable 不會改變 PR 上的任何東西：auto-merge 仍然開著。Conductor 的執行輸出 halt 與 `disable-auto-merge (#N)`。之後 `gh pr view N --json autoMergeRequest` 顯示沒有 | |
| F14 | 暫停狀態讀取失敗。這在真實的 GitHub 上不容易刻意製造。它由一個單元測試涵蓋，也可以從 `tools/agentctl/github.py` 的 `variable()` 讀出來：讀取失敗時會拋出錯誤，conductor 接著的行為等同暫停。這裡要確認的是 Conductor App 的 token 讀得到 repo variable。在 `CONDUCTOR_PAUSED` 沒有設定或是 `false` 的情況下，手動執行 conductor | 這次執行不會印出 `halt (treated as paused: cannot read the repository variable ...)`。如果印出來了，而且帶有 HTTP 403，表示這個 App 不能讀取 repo variable，每一輪的行為都會等同暫停 | |
| F15 | 具名開發者少了 secret。挑一個 sprint 檔指定給某位具名開發者（`assignee` 或 `[owners]`）、而且下一個 stage 是派到雲端的 story。在 `conductor` environment 裡刪掉那位開發者帶後綴的 secret（`CLAUDE_TRIGGER_URL_<LOGIN>` 或 `DISPATCH_TOKEN_<LOGIN>`，看那個 stage 用哪一個），並確認不帶後綴的那個存在。在 Actions 上執行 conductor。做完後把 secret 還原 | 派工失敗，訊息裡指出那位開發者："no https trigger URL configured for harness '...' and developer '...'"，或 "no dispatch token configured ..."。沒有寫入任何東西：story 的 issue 上沒有 marker 留言。沒有任何 session 用不帶後綴的 secret 啟動 | |
| F16 | 在 sandbox 裡進行的本機 Codex review。找一個 review stage 以 `via = "sbx"` 執行 Codex 的 story，讓 `conductor here` 派發這次 review。做兩次：一次在審查身分的帳號不在 repo variable `REVIEW_BOTS` 裡的時候，一次在它列在裡面的時候 | 只有送出 review 的那個身分的帳號列在 `REVIEW_BOTS` 裡時，這次 review 才會變成 `agent-review` status。不在名單上：review 出現在 PR 上，但沒有寫入 status。在名單上：`bridge` job 把 status 寫在被審查的 commit 上，這部分應該要「成功」。記下你實際看到的帳號名稱 | |
| F17 | Conductor 在 Actions 上的時候，執行 `bin/agentctl conductor here --dry-run`。比較執行前後的 `CONDUCTOR_HOME` 與 `CONDUCTOR_LEASE` | 它只跑一輪、印出計畫，然後結束。兩個 variable 都沒有改變，也沒有建立任何東西。這一項應該要「成功」 | |
