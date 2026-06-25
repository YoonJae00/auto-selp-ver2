# QML UI Release Checklist

This checklist is the release gate for the crawler QML desktop UI. Do not mark the QML redesign complete while any required row is FAIL.

## Required evidence format

| Platform | OS build | Display scale | Package version | Result | Fallback used | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| macOS local verification | TBD | 100% | dev | PENDING | color fallback or native effect | Local source run |
| macOS local verification | TBD | 200% | dev | PENDING | color fallback or native effect | Local source run |
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
| Startup | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | launch log or screenshot |
| Shutdown | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | app closes without stranded task |
| Dark/light theme | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | screenshots for both themes |
| Transparency or Mica fallback | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | fallback name and screenshot |
| Move, resize, minimize, maximize, and restore | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | screen recording or notes |
| Korean text rendering | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | screenshot |
| Korean input | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | typed field screenshot |
| First run | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | setup completion evidence |
| Keychain | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | save/load/remove result |
| Suppliers workflow | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | create/edit/delete smoke result |
| Adapter Studio workflow | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | probe/generate/save smoke result |
| Crawl workflow | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | category/product smoke result |
| Export workflow | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | xlsx output evidence |
| Monitor workflow | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | schedule/event smoke result |
| Settings workflow | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | settings save evidence |
| Active-task navigation | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | task remains visible after route change |
| Cancellation | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | cancellation result |
| Minimum size | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | minimum-size screenshot |
| Frozen launch | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | packaged/frozen launch result |
| Successful crawl/export smoke flow | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | crawl completes and exported workbook opens |

## macOS local verification

Record the OS build, Python version, display scale, package version or commit SHA, and whether the app ran from source or an installer-equivalent frozen launch.

- [ ] Startup
- [ ] Shutdown
- [ ] Dark/light theme changes
- [ ] Transparency or Mica fallback
- [ ] Move, resize, minimize, maximize, and restore
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
- [ ] 100% display scale
- [ ] 200% display scale
- [ ] Frozen launch

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
