# Extosoft Automation Standards (v0 — starter)

## Naming
- Test files: `<feature>.spec.ts` (Playwright) or `<feature>.robot` (Robot Framework)
- Test names: describe the user-visible behavior, not the implementation — `"user can reset password via email link"`, not `"test_reset_1"`

## Locator Strategy
- Prefer `getByRole`, `getByTestId`, or `getByLabel` over CSS/XPath selectors
- Never rely on nth-child or index-based selectors — they break on any layout change

## Structure (Page Object Model)
- One page object class per screen/route, under `pages/`
- Test files import page objects, never query the DOM directly

## Assertions
- One logical assertion per test where practical
- Assert on user-visible outcomes (`toBeVisible()`, `toHaveText()`), not internal state
