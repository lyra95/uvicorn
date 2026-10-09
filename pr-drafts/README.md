# Windows reload 수정 — 초안 모음

uvicorn 리로드가 Windows 에서 멈추는 문제(`Reloading...` 만 찍히고 코드 수정이
반영되지 않음)를 조사하면서 만든 브랜치와 글들이다.

## 권장 순서

1. **`comment-on-3081.md`** — 업스트림 PR
   [#3081](https://github.com/Kludex/uvicorn/pull/3081) 에 남길 코멘트.
   제대로 된 수정은 이미 거기 올라와 있고(콘솔 신호 대신 IPC 이벤트),
   콘솔 없는 환경에서 실제로 동작하는 것까지 확인했다. 다만 merge conflict 상태로
   2026-08-18 이후 멈춰 있다. 새 PR 보다 이쪽을 미는 게 값어치 있다.

2. **`branch-1-join-timeout.md`** — `fix/windows-reload-join-timeout` 브랜치의
   PR 본문. `join()` 에 타임아웃 + `kill()` 폴백. #3081 이 안 움직일 때의 스톱갭.
   비슷한 PR [#2947](https://github.com/Kludex/uvicorn/pull/2947) 이 닫힌 적이
   있어서, 그와 어떻게 다른지를 본문에서 정면으로 다룬다.

3. **`branch-2-process-group.md`** — `fix/windows-reload-process-group` 브랜치.
   `CTRL_BREAK_EVENT` 로 바꿔보는 방향인데 **동작하지 않는다.** 음성 결과
   보고서로 썼고 머지 대상이 아니다.

## 왜 별도 브랜치인가

이 파일들을 작업 브랜치에 두면 나중에 PR 을 열 때 디프에 같이 올라간다.
