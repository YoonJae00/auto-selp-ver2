# QML UI Release Checklist

This checklist is the release gate for the crawler QML desktop UI. Do not mark the QML redesign complete while any required row is FAIL.

## Required evidence format

| Platform | OS build | Display scale | Package version | Result | Fallback used | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| macOS local verification | macOS 26 | 100% | 3a6f38f | PASS | color fallback or native effect | User manual verification on macOS 26 |
| macOS local verification | macOS 26 | 200% | 3a6f38f | PASS | color fallback or native effect | User manual verification on macOS 26 |
| Windows 10 verification | TBD | 100% | release artifact | PENDING | native backdrop or color fallback | Installed package |
| Windows 10 verification | TBD | 125% | release artifact | PENDING | native backdrop or color fallback | Installed package |
| Windows 10 verification | TBD | 150% | release artifact | PENDING | native backdrop or color fallback | Installed package |
| Windows 10 verification | TBD | 200% | release artifact | PENDING | native backdrop or color fallback | Installed package |
| Windows 11 verification | TBD | 100% | release artifact | PENDING | Mica or safe fallback | Installed package |
| Windows 11 verification | TBD | 125% | release artifact | PENDING | Mica or safe fallback | Installed package |
| Windows 11 verification | TBD | 150% | release artifact | PENDING | Mica or safe fallback | Installed package |
| Windows 11 verification | TBD | 200% | release artifact | PENDING | Mica or safe fallback | Installed package |

Each matrix cell must be PASS, FAIL, or PENDING. Evidence must name the platform and display scale for each PASS or FAIL cell. A platform summary row can be PASS only when every required matrix cell for that platform and scale is PASS.

| Check | macOS 100% | macOS 200% | Windows 10 100% | Windows 10 125% | Windows 10 150% | Windows 10 200% | Windows 11 100% | Windows 11 125% | Windows 11 150% | Windows 11 200% | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Startup | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Shutdown | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Dark/light theme | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Transparency or Mica fallback | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Move, resize, minimize, maximize, and restore | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Korean text rendering | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Korean input | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| First run | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Keychain | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Suppliers workflow | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Adapter Studio workflow | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Crawl workflow | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Export workflow | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Monitor workflow | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Settings workflow | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Active-task navigation | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Cancellation | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Minimum size | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Frozen launch | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |
| Successful crawl/export smoke flow | PASS | PASS | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | macOS 26 user manual verification |

## macOS local verification

Record the OS build, Python version, display scale, package version or commit SHA, and whether the app ran from source or an installer-equivalent frozen launch.

- [x] Startup
- [x] Shutdown
- [x] Dark/light theme changes
- [x] Transparency or Mica fallback
- [x] Move, resize, minimize, maximize, and restore
- [x] Korean input
- [x] First run
- [x] Keychain
- [x] Suppliers workflow
- [x] Adapter Studio workflow
- [x] Crawl workflow
- [x] Export workflow
- [x] Monitor workflow
- [x] Settings workflow
- [x] Active-task navigation
- [x] Cancellation
- [x] Minimum size
- [x] 100% display scale
- [x] 200% display scale
- [x] Frozen launch

## Windows 10 verification

Run the GitHub Actions Windows package build or run `pyinstaller --clean build_windows.spec` on Windows 10. Install the generated package before testing.

- [ ] OS build recorded
- [ ] Package version recorded
- [ ] 100% display scale
- [ ] 125% display scale
- [ ] 150% display scale
- [ ] 200% display scale
- [ ] Startup
- [ ] Shutdown
- [ ] Dark/light theme
- [ ] Transparency or Mica fallback
- [ ] Move, resize, minimize, maximize, and restore
- [ ] Edge selection
- [ ] Korean text rendering
- [ ] Korean input
- [ ] First run
- [ ] Keychain
- [ ] Suppliers workflow
- [ ] Adapter Studio workflow
- [ ] Crawl workflow
- [ ] Export workflow
- [ ] Monitor workflow
- [ ] Settings workflow
- [ ] Active-task navigation
- [ ] Cancellation
- [ ] Minimum size
- [ ] Frozen launch
- [ ] Successful crawl/export smoke flow
- [ ] No console window

## Windows 11 verification

Install the same release artifact on Windows 11. Record whether Mica was applied or which fallback was used.

- [ ] OS build recorded
- [ ] Package version recorded
- [ ] 100% display scale
- [ ] 125% display scale
- [ ] 150% display scale
- [ ] 200% display scale
- [ ] Startup
- [ ] Shutdown
- [ ] Dark/light theme
- [ ] Transparency or Mica fallback
- [ ] Move, resize, minimize, maximize, and restore
- [ ] Korean text rendering
- [ ] Korean input
- [ ] First run
- [ ] Keychain
- [ ] Suppliers workflow
- [ ] Adapter Studio workflow
- [ ] Crawl workflow
- [ ] Export workflow
- [ ] Monitor workflow
- [ ] Settings workflow
- [ ] Active-task navigation
- [ ] Cancellation
- [ ] Minimum size
- [ ] Frozen launch
- [ ] Successful crawl/export smoke flow

## Required workflow smoke commands

Run before packaging:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
```

Run for the Windows package:

```bash
pyinstaller --clean build_windows.spec
```

## Result rules

- Use PASS only when the row was tested on the named OS and display scale.
- Use FAIL for any crash, missing QML module, missing asset, broken Korean text/input, inaccessible workflow, blocked cancellation, failed keychain operation, or incorrect native-effect fallback.
- Use PENDING until the evidence exists.
- Any FAIL blocks release completion.
