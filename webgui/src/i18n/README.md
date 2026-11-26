# Vision GUI localization

The station WebGUI uses one React language context, independent of authentication, API transport and module lifecycle. English is the source catalog; Polish is stored in `pl.json`. Add every new user-facing string to the catalog, including accessibility labels, errors and form metadata. Use `t(source, {parameter: value})` at render time, never store translated values in Core documents, API requests, module keys or persisted drafts.

The browser preference `vision.ui.language.v1` is UI-only. First visit selects Polish for a Polish browser locale, otherwise English. Settings and the signed-out page both offer a language selector. Changes apply immediately without remounting the workspace. API identifiers, operator-entered names, raw Core diagnostics, units and technical status codes remain authoritative and unchanged. Legacy LAB retains its English default.

Unit tests verify placeholder parity and schema metadata coverage; browser tests verify persistence and editing across language changes. Add matching translations when extending forms or introducing modules.
