# Obsidian `.gitignore` for vault version control
#
# Goal: keep your notes + plugins/themes settings + customizations, but exclude
# per-machine state (workspace layout, cache, plugin internal data, trash).

# Workspace layout (per-window state — never share)
.obsidian/workspace
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/workspace-tab-shops.json
.obsidian/cache/
.obsidian/themes/*/theme.css.map
.obsidian/plugins/*/data.json

# Trash (deleted notes)
.trash/

# OS junk
.DS_Store
Thumbs.db

# DO KEEP (negation rules below):
#   .obsidian/plugins/  — the plugin source code itself
#   .obsidian/themes/   — the theme files themselves
#   .obsidian/appearance.json
#   .obsidian/core-plugins.json
!.obsidian/plugins/
!.obsidian/themes/
!.obsidian/appearance.json
!.obsidian/core-plugins.json

# If you use Templater or other plugin-generated files, also ignore
# .obsidian/plugins/obsidian-templater/*/scripts/*  (templates stored per-machine)
# .obsidian/plugins/obsidian-dataview/*/cache.json

# Suggested vault directory layout (optional but useful for git history):
#   00-Inbox/         ← quick capture
#   10-Notes/         ← organized notes
#   20-Projects/      ← project-specific (e.g. 20-Projects/jonlink/)
#   30-Diary/         ← dated entries
#   40-Reference/     ← clipped articles / quotes
#   90-Archive/       ← read-only / completed
#
# Pure convention — git doesn't care about directory layout.