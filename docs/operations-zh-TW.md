# 日常運作

*English: [operations.md](operations.md)。兩份內容不一致時以英文版為準。*

專案設定完成之後的運作方式。設定的步驟在 [new-project-zh-TW.md](new-project-zh-TW.md) 與 [new-machine-zh-TW.md](new-machine-zh-TW.md)。

這裡的內容都還沒對真實的 GitHub 跑過。標示 **待驗證** 的地方，描述的是程式所依賴的 GitHub 本身的行為。

## 1. 日常

Conductor 在哪裡跑由你決定：在 GitHub Actions 上，或在你 Mac 的終端機裡。你在電腦前的時候，讓它在終端機裡跑。這樣不消耗 Actions 額度，反應也比較快（每三分鐘一輪）。

`conductor here` 需要的東西：

- **一份乾淨的 default branch checkout。** 當 checkout 裡的 `tools/`、`bin/`、`sandbox/` 或 `policy/` 與 default branch 不同時，它會拒絕啟動。請在 `main` 上執行，不要在審查中的 branch 上執行。每一輪它都從一份新的 `origin/main` 讀取 sprint、spec 與 policy，而不是從你的工作目錄讀。這項檢查防的是不小心在 agent 的 branch 上執行它的意外。它本身也是這些 script 的一部分，所以擋不住一份已經有敵意的 checkout。
- **一個放在 repository 之外的設定檔**，位置是 `~/.config/agent-dev/<owner>-<repo>/conductor.env`（如果你設了 `$XDG_CONFIG_HOME`，就在它底下而不是 `~/.config`）。它不可以放在專案目錄裡：sandbox 讀得到那裡的每個檔案，包含被 git 忽略的檔案。檔案內容是一行一個 `KEY=VALUE`：

```ini
# The Conductor App (new-project.md, section 3). The key path must be absolute; "~" is not expanded.
CONDUCTOR_APP_ID=123456
CONDUCTOR_APP_KEY=/Users/YOU/.config/agent-dev/OWNER-REPO/conductor-app.pem
# Your GitHub login. This conductor does not dispatch a story that the sprint file gives to someone else.
DEVELOPER=YOUR_LOGIN
# Dispatch credentials, the same values as the secrets in new-machine.md, section 3.
# Plain names here, whatever names they have on GitHub: on your Mac they are yours.
CLAUDE_TRIGGER_URL=https://...
CLAUDE_TRIGGER_TOKEN=...
DISPATCH_TOKEN=...
```

  `CONDUCTOR_APP_ID`、`CONDUCTOR_APP_KEY` 與 `DEVELOPER` 是必要的；少了它們，`here`、`away` 與 `status` 都會停下來並顯示訊息。派發用的憑證則依你使用的 harness 而定。它們只屬於你。在本機跑的 conductor 會派發 sprint 檔交給它的 `DEVELOPER` 的 story，以及沒有指定給特定人的 story（`default`）。屬於另一位開發者的 story，不論它的 harness 以哪種方式啟動，都會被延後，直到持有那個人憑證的 conductor 執行：他自己的，或 GitHub Actions 上的那一個。所以你的憑證絕不會被用在指名屬於別人的 story 上。
- 路徑上要有 `openssl`。它用來簽署取得 App token 的請求。

本機的 conductor 在 GitHub 上以 Conductor App 的身分行動，和 Actions 的 job 完全一樣：它用那把 key 自己產生 App 的 token。它不是以你的身分行動。如果是，它開的 pull request 的作者就會是你，而 GitHub 不允許作者核准自己的 pull request。

啟動：

```bash
bin/agentctl conductor here
```

想看它會做什麼、但不讓它真的做任何事，就加上 `--dry-run`。這會跑一輪、印出計畫然後結束。它不取得 lease，也不設定任何 variable，所以 GitHub Actions 上的 conductor 會照原樣繼續：

```bash
bin/agentctl conductor here --dry-run
```

離開前按 Ctrl-C，或在另一個終端機執行：

```bash
bin/agentctl conductor away
```

兩者都會立刻交接：把 `CONDUCTOR_HOME` 設為 `actions`，並在 Actions 上啟動一次 conductor 執行。

如果你只是把筆電闔上，就沒有任何交接。`CONDUCTOR_HOME` 是 `local` 的期間，Actions 上由事件觸發的執行會被跳過。只有排程的執行與手動啟動的執行會去看 lease，而且要等 lease 超過 20 分鐘沒有續期才會接手（`policy/conductor.toml` 的 `local_lease_minutes`）。排程的執行每四小時一次，所以空窗最長可能到大約四小時。想早點結束空窗，就在 20 分鐘過後，從任何裝置手動啟動一次執行：

```bash
gh workflow run conductor.yml
```

還有兩種情況會讓本機的 conductor 結束。Lease 只在成功的一輪之後續期；連續三輪失敗之後，它會把 `CONDUCTOR_HOME` 設回 `actions` 並結束。另外，如果同一個 repo 又啟動了第二個 `conductor here`，lease 上的名字會變成新的那一個，第一個會在它的下一輪停止。Repository variable 不是鎖：交接前後，兩個 conductor 可能重疊。兩者在送出每一次派發之前都會重新讀取 lease，如果 lease 已經換了對象，就停止自己的這一輪；這會縮小重疊，但無法消除它。派發是先記錄再送出，所以重疊可能讓同一個 stage 被送出兩次；它絕不會漏掉任何一次。

開發者不只一位時，要知道本機的 conductor 會留下哪些事不做。它派發它自己那位開發者的 story 與 `default` 的 story，也會做所有不屬於派發的事（開 pull request、把它們轉為可審、更新 branch）。Sprint 檔交給另一個指名的人的 story，不會從你的 Mac 派發。在你的 lease 還沒過期的期間，GitHub Actions 上排程的執行（每四小時一次）與手動啟動的執行會派發那些 story，其他什麼都不做；由事件觸發的執行仍然會被跳過。所以在你的 Mac 擔任 conductor 的期間，另一個人的雲端 stage 推進得很慢，而他在本機 sandbox 執行的 stage（`via = "sbx"`）完全不會推進，直到 `conductor here` 在他自己的 Mac 上執行。如果這有影響，就在你沒有主動盯著的時候交接給 Actions（`conductor away`）。

想知道它現在在哪裡跑：

```bash
bin/agentctl conductor status
```

| 情況 | 做法 |
|---|---|
| 想暫停一切 | 把 variable `CONDUCTOR_PAUSED` 設為 `true`。它在每一輪都是即時讀取的，所以本機的 conductor 也會在一輪之內停下來。暫停中的 conductor 不派發任何東西、不開 pull request，也不啟用 auto-merge。在它的下一輪，它還會把每個已開啟 auto-merge 的 open pull request 的 auto-merge 關掉；在那之前，這樣的 pull request 在 check 轉綠時，GitHub 仍然會自行合併它。要立刻停止，就在設定 variable 之後啟動一輪（`gh workflow run conductor.yml`），或自己把它關掉：`gh pr merge NUMBER --disable-auto`。解除暫停之後，conductor 會在適用的地方重新啟用 auto-merge。已經在執行的 session 不會因為暫停而停止。如果這個 variable 完全讀不到（網路或權限錯誤），conductor 的行為就如同被暫停 |
| 想知道現在的狀態 | 看 Director's brief issue，或執行 `bin/agentctl status --markdown` |
| 想知道 conductor 接下來會做什麼 | `gh workflow run conductor.yml -f dry_run=true`，然後看執行紀錄。Dry run 不會建立任何東西。暫停期間它只顯示 `halt` |
| 某個 story 被標上 `needs-human` | Conductor 會在 story issue 的留言裡提及人類；它不會把 issue 指派給任何人。讀 issue 上 triage 的說明與選項，做決定，然後移除 label；如果需要改 spec，就改 spec |
| 某個 harness 額度用盡 | 設定 `CONDUCTOR_QUOTA`；到期後 conductor 會自動恢復使用該 harness |
| 想讓某個 story 暫時不動 | 在它的 issue 加上 `blocked` label |
| 想發版 | 在 main 上你要的 commit 打 `v*` tag 並 push。除非 `ci`、`security` 與 `spec-verify` 在那個 commit 上都存在而且是綠的，否則 release 會失敗 |
| 想知道 Actions 用了多少 | `bin/agentctl budget --dry-run`，或看 brief 的第一行。這是估算；以 GitHub 的帳單頁面為準 |
| Actions 額度快用完了 | Overflow 是關閉的：`policy/conductor.toml` 的 `overflow_runner` 是空的，所以 `agentctl budget` 只回報用量，不搬動任何東西。額度用完時 CI 會停止，什麼都不會合併（**待驗證**）。你的選項：等到下個月；付費買更多分鐘數；或把 `overflow_runner` 設為一個專供這些 job 使用、不持有任何憑證、每個 job 都重新建立的 runner。`sandbox/` 裡的 Lima VM 不符合條件：`ci` 與 `security` 會執行 pull request 的程式碼，而那個 VM 是長期存在的、有免密碼的 sudo，還存著 agent 的登入資訊。讓 conductor 在本機跑（見上）可以省下它那一份分鐘數 |
| 某個 story 應該用特定某個人的訂閱來跑 | 在 sprint 檔裡指名：`assignee` 是整個 sprint 的預設，`[owners]` table 可以逐個 story 覆寫（`"012" = "alice"`）。Issue 的 assignee 不會被使用。交給指名的人的 story 只使用那個人的 secret（`NAME_LOGIN`）；少了其中一個，派發就會失敗並顯示訊息，什麼都不會送出 |
| 某個 review stage 必須在本機 sandbox 執行 | 在 `policy/roles.toml` 給那個 harness 設 `via = "sbx"`，並且不設 `review_workflow`。Sandbox 的 token 無法寫入 `agent-review` status；reviewer 會發表一則 pull request review，再由 `bridge` job 轉換。把負責 review 的那位開發者的 agent App 帳號（`yourname-agent[bot]`）加進 `REVIEW_BOTS` variable，否則這則 review 會被忽略 |
| 你核准了一個 spec 或 sprint pull request | 不用再做任何事。Conductor 會在它的下一輪替這個 pull request 啟用 auto-merge，check 全綠之後就會合併。在 Actions 上，那一輪是由 `risk-gate` 因你的 review 重新執行所啟動；在本機則是下一次輪詢。Conductor 暫停期間不會發生 |
| 一個 `chore/` pull request 可以合併了 | 自己合併。Conductor 絕不會合併 `chore/` 的 pull request |
| 需要修改 pipeline 本身 | 在 session 中直接要求 agent；工作在 `chore/` branch 上進行，由你核准 PR |
| 懷疑有異常 | 暫停，然後執行 [redteam-project-zh-TW.md](redteam-project-zh-TW.md) 與 [redteam-machine-zh-TW.md](redteam-machine-zh-TW.md) |

## 2. 開啟自動合併

這一節講的是 story 的 pull request。Code owner 核准過的 spec 或 sprint pull request，不論這個設定為何，conductor 都會替它啟用 auto-merge，因為合併的決定是人做的。沒有人需要 review 的 pull request 絕不會經由這條路被挑上，而 `chore/` 的 pull request 一律由人合併。

至少維持 shadow mode 一個 sprint。每次 conductor 通知你某個 PR「可以合併」時，花一分鐘自己判斷，記下你是否同意。持續同意一段時間之後，在 `policy/conductor.toml` 設定：

```toml
auto_merge_tiers = ["T0"]
```

再過一段時間，加上 `"T1"`。修改這個檔案本身是 T2，需要你核准。

## 3. 加入一個人

1. 他加入 organization，並成為 repo admin。
2. 在 `policy/roles.toml` 把他加進 `humans`，並給他一個 `[developers.LOGIN.stages]` table。在 `.github/CODEOWNERS` 把他加到他可以核准的路徑。只有在他要核准產品決定時，才把他加進 `directors` 與產品相關的路徑。
3. 他把 [new-machine-zh-TW.md](new-machine-zh-TW.md) 從頭到尾做完：他自己的 agent App、他自己的 secret、他的 sandbox 與他自己的雲端帳號。他的 secret 放在 `conductor` 這個 environment 裡，不是 repository secret，並以他的帳號作為後綴（大寫，其他字元一律換成 `_`）：`DISPATCH_TOKEN_ALICE`。指名交給他的 story 一定要有這個後綴；這類 story 絕不會使用不帶後綴名稱的 secret。
4. 屬於他的 story：在 sprint 檔的 `[owners]` table 裡指名（`"012" = "alice"`），或把他設為該 sprint 的 `assignee`。Conductor 就會使用他的 harness 設定、他的憑證與他的訂閱。在 story issue 上設定 assignee 沒有作用。別人 Mac 上的 conductor 會延後他的 story；它們由 GitHub Actions 上的 conductor 派發，或由他自己 Mac 上 `DEVELOPER` 設為他帳號的 `conductor here` 派發。在本機 sandbox 執行的 stage（`via = "sbx"`）只有在後一種情況才會啟動。
5. 產品決定仍然屬於 director：只有他們是 `docs/specs/`、`docs/sprints/` 與 `docs/product/` 的 owner。
