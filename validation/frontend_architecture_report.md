# Frontend Architecture Report — Tabayyun NotesOps
_Phase 6 · Module 1 audit (from the actual `frontend/src`)._

## Stack
React 19 · react-router-dom 7 · CRA (react-scripts 5) · Tailwind + shadcn/ui (Radix) ·
axios · cmdk-style command palette (hand-rolled) · lucide-react · sonner (toasts) ·
framer-motion · recharts. Bilingual RTL/LTR. Dark/light theme.

## Existing structure (reused, not replaced)
| Area | File | How Phase 6 extends it |
|---|---|---|
| Routing | `src/App.js` | added 10 protected routes; existing routes untouched |
| Shell + sidebar | `src/components/layout/AppShell.jsx` | nav regrouped into permission-aware sections; **all original items preserved**; added `<NotificationBell/>` to the header |
| Command palette | `src/components/CommandPalette.jsx` | added live global search (debounced) + recent searches; kept quick-jump actions |
| Auth | `src/contexts/AuthContext.jsx` | reused as-is (token in `localStorage`, axios interceptor) |
| i18n | `src/contexts/LanguageContext.jsx` | reused `t(ar,en)` everywhere |
| API client | `src/lib/api.js` | reused `api` axios instance (Bearer + X-Lang) |
| Realtime | `src/lib/useWebSocket.js` | reused for the bell's live unread refresh |

## Design language captured (and reused verbatim)
- **Page wrapper:** `p-6 lg:p-8 space-y-6` + a header (`label-mono` kicker + `text-3xl font-medium` title).
- **Cards:** `border border-border bg-card rounded-md`; section header `hairline px-5 py-3`; section label `label-mono`.
- **Figures:** `data-number`; lists `divide-y divide-border`, rows `px-5 py-3 hover:bg-secondary/50`.
- **Empty state:** `p-8 text-center text-sm text-muted-foreground`.
- **Buttons:** primary `bg-primary text-primary-foreground rounded-md`; ghost `border border-border hover:bg-secondary`.
- **Custom utilities:** `label-mono`, `data-number`, `hairline`, `glass` (kept).
- `data-testid` on interactive elements (followed for every new screen).

## Reusable components found
shadcn/ui kit (`src/components/ui/*`: button, card, table, dialog, dropdown-menu, tabs,
select, input, textarea, badge, skeleton, scroll-area, sonner…), plus app components
(CommandPalette, AIAssistantDrawer, ReminderBell, Timeline, GreetingCard, DailyExecutionBrief).

## Recommended extension points (used)
1. **A thin shared kit** (`src/components/kit.jsx`) wrapping the EXISTING classes
   (`PageHeader`, `Section`, `Stat`, `Modal`, `Field`, `Input/Select/Textarea`,
   `PrimaryButton/GhostButton`, `Badge`, `Empty/Loading/Forbidden`) — guarantees every new
   page is pixel-consistent with the originals while keeping each page small.
2. **Permission-aware nav** via a new `usePermissions()` hook (`GET /rbac/my-permissions`,
   cached) — feeds sidebar/command-palette visibility; pages still enforce server-side.
3. **Header notification bell** + **command-palette search** as the two highest-leverage,
   lowest-risk integration points (no new surfaces).

## Constraints honoured
No new design system, no new framework, no layout/navigation/sidebar redesign, no theme
change. New screens reuse the existing wrappers, cards, tables, forms, modal pattern,
typography, spacing, and command palette — indistinguishable from the original pages.
