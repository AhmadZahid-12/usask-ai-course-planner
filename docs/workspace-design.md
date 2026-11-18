# Student workspace visual direction

The original dashboard gave template progress, deadlines and utility links similar weight. On a phone, the calendar controls and month grid crowded the selected day’s agenda. The redesign opens up the page and lets the content determine the layout. Today and upcoming deadlines sit side by side on wide screens, and today comes first on a phone.

## Reference notes

Community previews are visual references. The implementation uses the project’s own Jinja templates, CSS and JavaScript.

| Reference | What to take into the workspace |
| --- | --- |
| [Dashboard Sidebar](https://21st.dev/@arunjdass/components/dashboard-sidebar) | Keep the navigation rail quiet. Use a bounded active row and group links by proximity. |
| [App 1](https://21st.dev/@shadcnstore/components/app-1) | Give the principal number and its explanation different scales. Use ruled sections where repeating stat cards would make the page harder to scan. |
| [Command](https://21st.dev/@shadcn/components/command) | Keep the search field in focus and the active result easy to spot. A visible slash shortcut makes the existing course search discoverable. |
| [Cell-to-Card Calendar Expansion](https://21st.dev/@aloksivastava1025/components/cue-cell-to-card-calendar-expansion) | Clicking a marked date expands it into an overlay. Keep that clear link in a fixed agenda so neighbouring dates remain visible. |
| [Timeline](https://21st.dev/@abui/components/timeline) | The zoom slider changes the density of the time columns. The coloured edge and small time label keep events legible when columns narrow. |
| [Rich Text Editor](https://21st.dev/@uvain/components/rich-text-editor-toolbar) | Leave uninterrupted space for writing. Match the scope of the existing plain-text notes with a quiet editor and one save action. |
| [Dialog](https://21st.dev/@originui/components/dialog) | Edit Profile focuses the first field and groups the confirmation at the bottom. Retain native dialogs and make focus and primary actions easy to find. |
| [Stretch Tabs](https://21st.dev/@dhxwhy/components/stretch-tabs) | Selecting Members moves the indicator between fixed tab slots. The workspace keeps the stable positions and uses a shorter state change. |
| [Dropdown Menu](https://21st.dev/@originui/components/dropdown-menu) | The edit menu is a short, evenly spaced list with light elevation. Native selects cover the workspace’s simple filters with keyboard support. |
| [Sidebar](https://21st.dev/@wensity/components/sidebar) | Keep icon and label positions stable. Reserve the active treatment for the current section. |

[Linear](https://linear.app/now/behind-the-latest-design-refresh) describes a hierarchy where structure recedes behind work. [Raycast](https://www.raycast.com/) shows how shortcuts can sit alongside descriptive labels. [Vercel](https://vercel.com/changelog/dashboard-navigation-redesign-rollout) uses a persistent rail for navigation. [Notion](https://www.notion.com/product/docs) gives prose room to breathe.

## Identity explorations

[Compare the three marks and wordmarks](workspace-brand-directions.svg).

- **Meridian** uses orthogonal paths that meet at a point. It connects the academic pathway and the act of choosing where to go next. This is the provisional direction used in the workspace.
- **Interval** frames three ticks within a time window. It communicates calendar and sequencing, with a narrower scope than the product.
- **Margin** pairs an offset page edge with two aligned lines. It captures the study and writing experience but gives less emphasis to navigation and progress.

The live wordmark remains **Course Planner** with **USask workspace** beneath it. Use the original geometric mark on a cobalt square with a warm-white line. Allow at least a quarter of the mark’s width around it when it stands alone. The same simplified SVG works as the favicon.

Inter continues to carry labels, navigation, forms and prose. Instrument Serif is reserved for page titles, major section headings and the progress figure. Use tabular or monospace numerals for dates and course identifiers. Both faces are served locally with their SIL Open Font licenses.

Use one accent for selection, links and primary actions. Theme tokens pair graphite and warm white with cobalt in light mode and soft periwinkle in dark mode. Semantic hues are reserved for categories and statuses. Use a 6px radius for most surfaces, thin rules for sections, and elevation for dialogs. Control transitions are around 160–170ms, with decorative motion gated by the reduced-motion preference.
