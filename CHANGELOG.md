# Changelog

## v1.5

- Added true Grid, Horizontal, and Vertical composition layouts to Auto Frame.
- Grid mode now defaults to an automatic square-ish column count (9 images → 3×3) and supports manual column counts.
- Added independent ordering controls: As added, Chronological (oldest first), and Reverse chronological (newest first).
- Added per-row selection checkboxes plus Select all / Select none controls.
- Added bulk model and color editing for All screenshots or Selected screenshots.
- Bulk model choices are restricted to variants compatible with every targeted screenshot resolution.
- Preview, Merge all, and Batches now use the same chosen order and arrangement.
- Retained v1.4 safe icon embedding and v1.2 automatic orientation correction.

## v1.4

- Removed unsafe post-build EXE resource patching that could corrupt PyInstaller's appended one-file archive.
- Added verified build checks for output size and embedded PyInstaller archive integrity.
- Fixed runtime Tk/CustomTkinter icon handling.
- Added a multi-resolution Windows application icon and version metadata.
- Bumped the Windows AppUserModelID.

## v1.3

- Experimented with post-build icon-resource replacement. This approach was removed in v1.4 because it could damage one-file PyInstaller executables.

## v1.2

- Made screenshot pixel dimensions the source of truth for portrait/landscape detection.
- Automatically rotates frame and mask assets when their stored orientation does not match the screenshot orientation.
- Removed the frame-asset attribution footer from the application UI.

## v1.1

- Improved landscape handling for frame assets stored with unexpected pixel orientation.
- Added custom application icon support.

## v1.0

- Initial Apple Frames Studio Windows GUI.
- Automatic device detection from screenshot resolution.
- Device variants and frame colors.
- Mixed-device compositions and proportional physical scaling.
- Multi-file, folder, individual, merged and batch workflows.
- Retained the original Manual Grid / Tight Grid renderer.
