# AI Inbox Acceptance Quickstart

## Goal

Use this short checklist when you want to quickly verify the `AI review + unified message center + inbox` flow without reading the full product docs.

## Fast Demo

Run the canned demo suite:

```powershell
.\tools\run_ai_inbox_demo_suite.ps1
```

It will generate three scenario outputs under `exports\demo_ai_inbox_<timestamp>`:

- `default.txt`
- `triage.txt`
- `resolved.txt`

## Live App Check

Launch the app normally and focus on the recommendation page.

### 1. AI Review

- Confirm the configuration page has valid OpenAI settings.
- Trigger one manual AI review.
- Check that:
  - output streams into the AI panel
  - the status banner updates
  - the unified message center receives an AI event

### 2. Message Center

- Confirm the recommendation tab shows a counter like `推荐(x/y)`.
- On the recommendation page, confirm the message center shows:
  - summary label
  - unread/open badge
  - metric cards
  - event table
  - detail panel

### 3. Inbox Actions

- Select an unread event and confirm it becomes read.
- Use:
  - `标已读`
  - `标已办`
  - `全标已读`
  - `清已办`
- Toggle `只看待办` and confirm the table filters correctly.

### 4. Sorting

- Switch between:
  - `最新优先`
  - `未读优先`
  - `待处理优先`
  - `异常优先`
- Confirm the first row changes in a reasonable way.

### 5. Routing

- For a trade event, confirm the main action prefers the broker / execution page.
- For an AI error with an API key issue, confirm the action prefers the config page.
- For a message event tied to a symbol, confirm the action prefers the recommendation page.

## Expected Outcome

The recommendation page should now behave like:

1. Research workspace
2. Event inbox
3. Lightweight dashboard

## Related Docs

- [RELEASE_NOTES_2026-04-19_AI_INBOX.md](C:/Users/18335/Documents/New%20project/docs/RELEASE_NOTES_2026-04-19_AI_INBOX.md)
- [iteration-85-ai-review-and-message-center-inbox.md](C:/Users/18335/Documents/New%20project/docs/product/iteration-85-ai-review-and-message-center-inbox.md)
- [iteration-86-message-center-dashboard-and-sort.md](C:/Users/18335/Documents/New%20project/docs/product/iteration-86-message-center-dashboard-and-sort.md)
- [iteration-87-demo-and-acceptance-playbook.md](C:/Users/18335/Documents/New%20project/docs/product/iteration-87-demo-and-acceptance-playbook.md)
