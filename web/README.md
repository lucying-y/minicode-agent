# Web Console Frontend

`web/` contains the React/Vite frontend for the local MiniCode Agent Console.
It consumes the FastAPI endpoints exposed by `src/minicode_agent/web` and uses
SSE to append the persisted run timeline as events arrive.

## Commands

```bash
npm ci
npm test
npm run build
```

The production bundle is written to `web/dist` and is served by
`uv run minicode web`. The frontend is intentionally kept separate from the
Python runtime bundles: model calls, permissions, persistence, and shell
execution all remain backend responsibilities.

This documentation pass does not add inline comments to the frontend source.
