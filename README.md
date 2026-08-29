# Apple Frames Studio

A modern Windows desktop app for framing screenshots with Apple device frames, composing multiple devices in one image, and building large framed screenshot grids.

Apple Frames Studio combines an automatic resolution-driven framing workflow with the original **Tight Grid** composer. It is designed for Windows and can be packaged as a single self-contained `.exe` with PyInstaller.

> **Current version:** 1.5

## Features

### Auto Frame

- Automatically detects supported devices from screenshot resolution.
- Determines **portrait vs. landscape from the screenshot's pixel dimensions**, rather than trusting the frame asset filename.
- Automatically rotates frame and mask assets when an asset's stored orientation disagrees with the screenshot orientation.
- Supports shared-resolution **device variants**.
- Supports device **frame colors**, including random color selection where available.
- Add one screenshot, many screenshots, or an entire folder in one shot.
- Compose mixed devices together.
- Optional proportional physical scaling when combining different device classes.
- Merge all screenshots, export individual framed images, or process sequential batches.
- Arrange compositions as a **Grid**, **Horizontal strip**, or **Vertical stack**.
- Grid mode supports automatic square-ish layout or a manually selected column count.
- Output order can be **As added**, **Chronological (oldest first)**, or **Reverse chronological (newest first)**.
- Bulk-edit the device model and color for **all screenshots** or only **selected screenshots** using row checkboxes — practical for sets of 100–200+ images.

### Manual Grid

- Original Tight Grid workflow retained.
- Auto / original / forced portrait / forced landscape orientation modes.
- Tight or uniform-cell layout.
- Automatic or manual column count.
- Independent or locked horizontal/vertical gaps.
- Custom background color.
- Screen inset, corner radius, fill scale, and frame placement controls.
- Multi-threaded rendering.
- Canvas/RAM estimate and cancellable rendering.

### Export

- PNG
- JPEG
- WebP
- TIFF
- BMP
- PDF
- Optional HEIF/HEIC copy when `pillow-heif` is available

## Supported devices

Support is driven by the Apple Frames metadata contained in the frame asset library rather than a hard-coded device list. The current library includes a wide range of iPhone, iPad, Apple Watch, MacBook, iMac, and Apple display frames.

When multiple device generations use the same screenshot resolution, Apple Frames Studio exposes compatible device variants so you can choose the frame you actually want.

## Frame assets

Frame assets are **not stored in this repository**.

The build script and the in-app Frame Library updater can retrieve the current Apple Frames asset pack from the MacStories CDN:

```text
https://cdn.macstories.net/AppleFrames401.zip
```

If `Frames.zip` is already beside `BUILD_APP.bat`, the builder uses that local copy instead.

## Build the Windows app

### Requirements

- Windows 10 or Windows 11
- Python 3.10+
- Internet access on the first build if `Frames.zip` is not already present

### Easiest method

1. Clone or download this repository.
2. Double-click `BUILD_APP.bat`.
3. The builder installs/updates the Python dependencies, generates the multi-resolution custom icon, downloads the frame assets if needed, and builds the EXE.
4. The finished application is created at:

```text
dist\AppleFramesStudio.exe
```

To force a fresh frame-asset download before building:

```bat
BUILD_APP.bat refresh
```

The builder validates the generated one-file executable before reporting success. A valid build should normally be tens of megabytes because the frame library is embedded into the final EXE.

## Build from the command line

The project uses:

```text
pillow
pillow-heif
customtkinter
pyinstaller
```

The app is packaged with PyInstaller in `--onefile --windowed` mode. The custom PNG/ICO resources are generated reproducibly by `generate_icon.py` before packaging. Windows version information is embedded at build time, and the completed EXE is deliberately **not modified afterward**, because post-build PE resource rewriting can corrupt PyInstaller's appended one-file archive.

## GitHub Actions

A Windows build workflow is included under `.github/workflows/build-windows.yml`.

Open **Actions → Build Windows EXE → Run workflow** to produce a verified Windows executable as a downloadable workflow artifact. The workflow generates the app icons and downloads the frame library before building.

## Project layout

```text
Apple-Frames-For-Windows-/
├─ apple_frames_studio.py       # Modern CustomTkinter GUI
├─ frames_engine.py             # Detection, framing, scaling and grid engine
├─ generate_icon.py             # Reproducible PNG + multi-resolution ICO generator
├─ version_info.txt             # Windows version metadata
├─ BUILD_APP.bat                # Windows one-click builder
├─ REFRESH_ICON_CACHE.bat       # Optional Explorer icon refresh helper
├─ requirements.txt
├─ CHANGELOG.md
├─ LICENSE
└─ .github/workflows/
   └─ build-windows.yml
```

Generated locally during build and intentionally ignored by Git:

```text
apple_frames_studio.ico
apple_frames_studio_icon.png
Frames.zip
```

## Bulk editing large screenshot sets

Every screenshot row has a selection checkbox. The Bulk Edit bar can target either all screenshots or only the checked rows. Compatible device variants are calculated across the target set, preventing an incompatible frame model from being applied to mixed resolutions.

For example, if 200 screenshots are all detected as `iPhone 16 Landscape` and the resolution also supports `iPhone 15 Pro Landscape`, choose **All screenshots → iPhone 15 Pro Landscape → Apply to target** once instead of editing 200 dropdowns.

## Composition layout and order

Ordering and arrangement are independent:

- **Order:** As added / Chronological / Reverse chronological
- **Arrangement:** Grid / Horizontal / Vertical
- **Grid columns:** blank for automatic layout or set an exact number

Chronological ordering uses each file's modified timestamp. The chosen order and arrangement are shared by Preview and Export so the saved result matches the preview.

## Orientation handling

Some frame-library files may contain names such as `Landscape` while the PNG itself is physically stored in portrait orientation, or vice versa. Apple Frames Studio therefore treats the **screenshot resolution as the source of truth**:

```text
width > height  -> landscape
height > width  -> portrait
```

The selected frame and its mask are then normalized to match that orientation before compositing.

## Credits

Apple Frames Studio is an independent Windows project inspired by the workflow and metadata-driven design of **Apple Frames 4** by Federico Viticci / MacStories.

Apple Frames and its frame asset library are provided by MacStories. Apple product names and trademarks belong to Apple Inc. This project is not an official Apple or MacStories application.

## License

The source code in this repository is released under the [MIT License](LICENSE). Third-party frame assets downloaded separately are not covered by this repository's MIT license.
