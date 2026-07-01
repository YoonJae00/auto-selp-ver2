# 안전한 부분 커밋(scoped commit) 체크리스트

워킹트리에 서로 얽힌 여러 작업이 섞여 있는데 그중 **한 덩어리만** 커밋해야 할 때 쓰는 절차.
순진하게 `git add <일부> && git commit` 하면 숨은 import 의존 때문에 커밋이 깨질 수 있다.

## 1. 언제 쓰나

- 워킹트리에 여러 기능/작업의 변경이 섞여 있고, 그중 일부만 골라 커밋해야 할 때.
- **`git add -A` 금지.** 무관한 변경까지 딸려 들어간다.

## 2. 절차

1. **파악** — `git status`로 전체 변경을 보고, "이번 커밋 대상"과 무관 변경을 구분한다.
2. **범위 합의** — 어디까지 포함할지 애매하면 사용자에게 확인한다.
3. **스테이징** — 대상 파일만 명시적으로 추가.
   ```bash
   git add path/a.py path/b.py tests/test_a.py ...
   ```
4. **격리** — 나머지를 치우고 워킹트리에 "스테이징한 부분집합"만 남긴다.
   ```bash
   git stash push --keep-index -u -m "non-target-work"
   ```
   → 제외한 tracked 파일은 HEAD로 되돌아가고, 미추적 파일은 stash로 치워진다.
5. **검증 루프** — 부분집합만으로 전체 테스트를 돌린다.
   ```bash
   cd crawler && python -m pytest tests/
   ```
   - **ImportError / 수집 에러 / 실패**가 나면, 제외한 파일에 대한 **숨은 의존**이다.
     그 파일을 stash에서 끌어와 커밋 대상에 추가한다:
     ```bash
     # tracked 파일 (경로는 '현재 셸 cwd 기준' 상대경로!)
     git checkout stash@{0} -- app/crawlers/yaml_adapter.py
     # 미추적 신규 파일 (미추적은 stash의 3번째 부모에 있음)
     git checkout stash@{0}^3 -- tests/test_new.py
     git add app/crawlers/yaml_adapter.py tests/test_new.py
     ```
   - **초록불이 될 때까지 5번을 반복**한다.
6. **커밋** — 여러 줄 메시지는 heredoc으로.
   ```bash
   git commit -F - <<'EOF'
   feat(scope): 요약

   본문...

   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
   EOF
   ```
7. **복원** — 제외해둔 나머지 작업을 되살린다.
   ```bash
   git stash pop
   ```
8. **정리** — 커밋 내용과 잔여 변경을 확인한 뒤 stash를 버린다.
   ```bash
   git show --stat HEAD
   git status
   git stash drop      # pop이 정상 복원됐음을 확인한 뒤에만
   ```

## 3. 함정 (실제로 걸렸던 것들)

- **숨은 의존 사슬** — 부분집합만으로 테스트하지 않으면 놓친다. `A → B → C` 식으로 import가 이어져
  하나 빼면 커밋이 import 에러로 깨진다. **4~5단계(격리 + 테스트)가 이 실수를 잡는 핵심 안전망.**
- **`stash pop` 충돌 걱정은 대체로 없음** — 커밋한 파일 = stash 버전(그 파일을 stash에서 그대로 끌어왔으므로)이라
  3-way merge에서 `ours == theirs` → 자동 병합된다.
  단, **이미 커밋된 미추적 파일**이 있으면 pop이 `already exists`로 *미추적 복원만* 부분 실패할 수 있다.
  이 경우에도 tracked 변경은 정상 적용되니, 미추적 파일들이 실제로 워킹트리에 있는지 직접 확인하고 진행한다.
- **`git stash drop`이 자동 차단될 수 있음** — 되돌릴 수 없는 로컬 삭제로 분류되어 막히면, pop이 성공했고
  파일이 모두 복원됐음을 먼저 확인한 뒤 **사용자에게 직접 실행하도록 안내**한다.
- **cwd 주의** — `git checkout stash@{0} -- <경로>`의 경로는 저장소 루트가 아니라 **현재 셸 cwd 기준**이다.
  cwd가 `crawler/`면 `app/...`, 루트면 `crawler/app/...`. 불일치 시 `did not match any file(s)`.

## 4. 사례 (2026-07, picker/매핑 커밋)

picker/매핑 관련 24개 파일만 커밋하려 했으나, 검증 루프에서 의존이 연쇄로 드러났다:

```
adapter_studio → workers/adapter → yaml_adapter → diagnostics.log_exception
                                  ↘ test_login_helper → site_probe (로그인 실패 동작)
```

`yaml_adapter.py`, `diagnostics.py`, `site_probe.py`를 stash에서 끌어와 함께 넣고서야 `302 passed`.
격리 + 테스트 절차가 없었으면 커밋이 그대로 깨졌을 것.
