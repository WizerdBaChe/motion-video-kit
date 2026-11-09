# Claim lines of the worked example (derived)

The original film's research notes are not shipped. Each line below is a claim text the
example `film.timeline.json` cites as `research:<text>`; `tl.py validate` (TV-9a) looks for it
on one line of this file. They record what the film says, not where it was verified.

- 一個來源的工作，分給多個執行者同時做
- 寬幅 fan-out 可在所有 worker 還在半途時把預算燒光
- Claude Code 預設同時 20 個子代理在跑時再生一個會失敗
- HTTP 429 表示在給定時間內請求太多
- 長駐、固定大小的一組 worker，從共用的佇列取工作
- 3 個 worker、5 個各 1 秒的工作，程式約 2 秒完成
- 同時問 100 台時約 63% 的使用者請求超過 1 秒
- Go `errgroup` 的 `Group.Go` 在達到上限時會阻塞到有空位
