# Vision GUI direction samples

Status: DESIGN PREVIEW. Two comparable views of the same empty ECU profile form.

- Carbon: real `@carbon/react` components with IBM Plex Sans.
- Fluent 2: real Fluent UI React v9 components.
- Shared fields, required-field feedback and local preview actions.
- Separate HTML entry points keep the two design systems' CSS independent.
- No Vision API requests, Core connections, device access or library writes.
- Form values are retained only in this browser tab's session storage under
  `vision.gui-samples.v1`, so a style switch preserves the comparison.
- The create/save action records only a preview snapshot in that same browser
  tab. It does not create an ECU catalog entry or a production draft.
- Blank starting form; only the revision label `r1` is initialized.
- No private station configuration, production measurements or branded assets.

## Development

Use the authorized Vision development host and an isolated worktree. Follow
the repository's AGENTS.md and development rules.

```sh
npm ci
npm run build
```

The build produces `dist/carbon.html`, `dist/fluent.html` and assets using the
`/design/` base. An isolated preview server may map these to
`/design/carbon/` and `/design/fluent/`. Keep this preview outside production.

## Design references

- https://www.carbondesignsystem.com/building-blocks/core/patterns/forms
- https://www.carbondesignsystem.com/building-blocks/foundations/typography/style-strategies
- https://fluent2.microsoft.design/components/web/react
- https://fluent2.microsoft.design/layout

The samples are design proposals for Vision, not official IBM or Microsoft products.
