# Grotto Single-Window Chrome

This Grotto-owned Linux feature makes the primary ChatGPT Desktop window a
single-window surface without removing useful application menus.

It reuses the pinned wrapper's tested frameless-titlebar main-process patch to
remove Electron's minimize, maximize, and close overlay. It deliberately does
not enable the upstream feature's webview patch, so File, Edit, View, and the
other application menus remain available.

The feature also guards the File menu's multi-window insertion so `New Window`
is omitted on Linux. Both main-bundle descriptors are required: if the pinned
application changes either source shape, the container build fails instead of
silently restoring the controls.
