from __future__ import annotations

import json
import math
import os
import random
import shutil
import ssl
import stat
import tempfile
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from PIL import Image, ImageDraw, ImageFile, ImageOps

Image.MAX_IMAGE_PIXELS = None
ImageFile.LOAD_TRUNCATED_IMAGES = True

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except Exception:  # Pillow < 9
    RESAMPLE_LANCZOS = Image.LANCZOS

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_OK = True
except Exception:
    HEIF_OK = False

APP_NAME = "AppleFramesStudio"
ASSETS_URL = "https://cdn.macstories.net/AppleFrames401.zip"
SUPPORTED_INPUTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif", ".jxl"
}

# Same default variant order used by Apple Frames 4 / frames-cli.
FRAME_VARIANTS = {
    "iPhone 17 Portrait": ["iPhone 17 Pro Portrait", "iPhone 17 Portrait", "iPhone 16 Pro Portrait"],
    "iPhone 17 Landscape": ["iPhone 17 Pro Landscape", "iPhone 17 Landscape", "iPhone 16 Pro Landscape"],
    "iPhone 17 Pro Max Portrait": ["iPhone 17 Pro Max Portrait", "iPhone 16 Pro Max Portrait"],
    "iPhone 17 Pro Max Landscape": ["iPhone 17 Pro Max Landscape", "iPhone 16 Pro Max Landscape"],
    "iPhone 16 Portrait": ["iPhone 16 Portrait", "iPhone 15 Pro Portrait"],
    "iPhone 16 Landscape": ["iPhone 16 Landscape", "iPhone 15 Pro Landscape"],
    "iPhone 16 Plus Portrait": ["iPhone 16 Plus Portrait", "iPhone 15 Pro Max Portrait"],
    "iPhone 16 Plus Landscape": ["iPhone 16 Plus Landscape", "iPhone 15 Pro Max Landscape"],
    "MacBook Pro M5 14": ["MacBook Pro M5 14", "MacBook Pro 2021 14"],
    "MacBook Pro M5 16": ["MacBook Pro M5 16", "MacBook Pro 2021 16"],
    "MacBook Air M5 13": ["MacBook Air M5 13", "MacBook Air 2022"],
    "Studio Display": ["Studio Display", "Studio Display XDR"],
    "Watch Series 11 42": ["Watch Series 11 42", "Watch Series 10 42"],
    "Watch Series 11 46": ["Watch Series 11 46", "Watch Series 10 46"],
}

# Ordered defaults matter: first item is the default color, matching Apple Frames 4.
FRAME_COLORS = {
    "iPhone 17 Pro Portrait": ["Cosmic Orange", "Deep Blue", "Silver"],
    "iPhone 17 Pro Landscape": ["Cosmic Orange", "Deep Blue", "Silver"],
    "iPhone 17 Pro Max Portrait": ["Cosmic Orange", "Deep Blue", "Silver"],
    "iPhone 17 Pro Max Landscape": ["Cosmic Orange", "Deep Blue", "Silver"],
    "iPhone 17 Portrait": ["Black", "Lavender", "Mist Blue", "Sage", "White"],
    "iPhone 17 Landscape": ["Black", "Lavender", "Mist Blue", "Sage", "White"],
    "iPhone Air Portrait": ["Black", "White", "Gold", "Blue"],
    "iPhone Air Landscape": ["Black", "White", "Gold", "Blue"],
    "MacBook Pro M5 14": ["Silver", "Space Black"],
    "MacBook Pro M5 16": ["Silver", "Space Black"],
    "MacBook Neo": ["Blush", "Citrus", "Indigo", "Silver"],
    "iPhone 16 Pro Portrait": ["Natural", "Desert", "Black", "White"],
    "iPhone 16 Pro Landscape": ["Natural", "Desert", "Black", "White"],
    "iPhone 16 Pro Max Portrait": ["White", "Desert", "Natural", "Black"],
    "iPhone 16 Pro Max Landscape": ["Black", "Desert", "Natural", "White"],
    "iPhone 16 Portrait": ["Ultramarine", "Teal", "Pink", "Black", "White"],
    "iPhone 16 Landscape": ["Ultramarine", "Teal", "Pink", "Black", "White"],
    "iPhone 16 Plus Portrait": ["Ultramarine", "White", "Teal", "Pink", "Black"],
    "iPhone 16 Plus Landscape": ["Ultramarine", "Teal", "Pink", "Black", "White"],
    "Watch Ultra 3": [
        "Black + Alpine Loop Black", "Black + Alpine Loop Light Blue", "Black + Milanese Loop",
        "Black + Ocean Band Anchor Blue", "Black + Ocean Band Black", "Black + Trail Loop Black Charcoal",
        "Natural + Alpine Loop Light Blue", "Natural + Alpine Loop Terra Cotta", "Natural + Milanese Loop",
        "Natural + Ocean Band Anchor Blue", "Natural + Ocean Band Neon Green",
        "Natural + Trail Loop Blue Bright Blue", "Natural + Trail Loop Green Neon",
    ],
    "Watch Ultra 2024": [
        "Orange Beige Trail Loop", "Blue Alpine Loop", "Orange Ocean Band", "Black + Alpine Loop Dark Green",
        "Black + Alpine Loop Navy", "Black + Alpine Loop Tan", "Black + Ocean Band Black",
        "Black + Ocean Band Ice Blue", "Black + Ocean Band Navy", "Black + Titanium Milanese Loop",
        "Black + Trail Loop Black", "Black + Trail Loop Blue", "Black + Trail Loop Green",
        "Natural + Alpine Loop Dark Green", "Natural + Alpine Loop Navy", "Natural + Alpine Loop Tan",
        "Natural + Ocean Band Black", "Natural + Ocean Band Ice Blue", "Natural + Ocean Band Navy",
        "Natural + Titanium Milanese Loop", "Natural + Trail Loop Black", "Natural + Trail Loop Blue",
    ],
    "MacBook Air M5 13": ["Midnight", "Silver", "Sky Blue", "Starlight"],
    "MacBook Air M5 15": ["Midnight", "Silver", "Sky Blue", "Starlight"],
    "iMac M4": ["Silver", "Blue", "Green", "Orange", "Pink", "Purple", "Yellow"],
    "Studio Display": ["Light", "Dark"],
    "Studio Display XDR": ["Light", "Dark"],
    "Watch Series 11 42": [
        "Aluminum Jet Black + Sport Band Black", "Aluminum Jet Black + Sport Loop Dark Gray",
        "Aluminum Rose Gold + Sport Band Light Blush", "Aluminum Rose Gold + Sport Loop Purple Fog",
        "Aluminum Silver + Sport Band Neon Yellow", "Aluminum Silver + Sport Band Purple Fog",
        "Aluminum Silver + Sport Loop Forest", "Aluminum Silver + Sport Loop Neon Yellow",
        "Aluminum Space Gray + Sport Band Anchor Blue", "Aluminum Space Gray + Sport Band Black",
        "Aluminum Space Gray + Sport Loop Anchor Blue", "Aluminum Space Gray + Sport Loop Forest",
        "Titanium Gold + Magnetic Link Sage Gray", "Titanium Gold + Milanese Loop",
        "Titanium Gold + Sport Band Light Blush", "Titanium Gold + Sport Band Purple Fog",
        "Titanium Natural + Magnetic Link Caramel", "Titanium Natural + Milanese Loop",
        "Titanium Natural + Sport Band Stone Gray", "Titanium Slate + Magnetic Link Navy",
        "Titanium Slate + Milanese Loop", "Titanium Slate + Sport Band Black",
    ],
    "Watch Series 11 46": [
        "Aluminum Jet Black + Sport Band Black", "Aluminum Jet Black + Sport Loop Dark Gray",
        "Aluminum Rose Gold + Sport Band Light Blush", "Aluminum Rose Gold + Sport Loop Purple Fog",
        "Aluminum Silver + Sport Band Neon Yellow", "Aluminum Silver + Sport Band Purple Fog",
        "Aluminum Silver + Sport Loop Forest", "Aluminum Silver + Sport Loop Neon Yellow",
        "Aluminum Space Gray + Sport Band Anchor Blue", "Aluminum Space Gray + Sport Band Black",
        "Aluminum Space Gray + Sport Loop Anchor Blue", "Aluminum Space Gray + Sport Loop Forest",
        "Titanium Gold + Magnetic Link Sage Gray", "Titanium Gold + Milanese Loop",
        "Titanium Gold + Sport Band Light Blush", "Titanium Gold + Sport Band Purple Fog",
        "Titanium Natural + Magnetic Link Caramel", "Titanium Natural + Milanese Loop",
        "Titanium Natural + Sport Band Stone Gray", "Titanium Slate + Magnetic Link Navy",
        "Titanium Slate + Milanese Loop", "Titanium Slate + Sport Band Black",
    ],
}


def local_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME}"


def safe_resource_path(name: str) -> Path | None:
    try:
        import sys
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        p = root / name
        return p if p.exists() else None
    except Exception:
        return None


def _zip_member_is_symlink(member: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(member.external_attr >> 16)


def _safe_extract_frames(zip_path: Path, destination: Path) -> Path:
    """Extract an Apple Frames archive safely and return its Frames root."""
    with tempfile.TemporaryDirectory(prefix="afs_extract_") as td:
        stage = Path(td)
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = []
            top_items = set()
            for m in zf.infolist():
                filename = m.filename.replace("\\", "/")
                if not filename or filename.startswith("__MACOSX/"):
                    continue
                if _zip_member_is_symlink(m):
                    raise ValueError(f"Unsupported symlink in archive: {filename}")
                pp = PurePosixPath(filename)
                if pp.is_absolute() or ".." in pp.parts:
                    raise ValueError(f"Unsafe archive path: {filename}")
                members.append((m, pp))
                top_items.add(pp.parts[0])
            prefix = next(iter(top_items)) if len(top_items) == 1 else None
            for m, pp in members:
                parts = list(pp.parts)
                if prefix and parts and parts[0] == prefix:
                    parts = parts[1:]
                if not parts:
                    continue
                target = stage.joinpath(*parts)
                if m.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(m) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        roots = [stage] if (stage / "NewFrames.json").exists() else [p.parent for p in stage.rglob("NewFrames.json")]
        if not roots:
            raise ValueError("NewFrames.json was not found in the frame archive.")
        root = roots[0]
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root, destination)
    return destination


class AssetManager:
    def __init__(self):
        self.data_root = local_data_root()
        self.frames_dir = self.data_root / "Frames"
        self.config_file = self.data_root / "config.json"
        self._bootstrap_if_needed()

    @staticmethod
    def valid_frames(path: Path | None) -> bool:
        return bool(path and path.exists() and (path / "NewFrames.json").exists())

    def _read_config(self) -> dict:
        try:
            if self.config_file.exists():
                return json.loads(self.config_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _write_config(self, cfg: dict) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def _bootstrap_if_needed(self) -> None:
        cfg = self._read_config()
        custom = Path(cfg.get("custom_frames_path", "")) if cfg.get("custom_frames_path") else None
        if self.valid_frames(custom) or self.valid_frames(self.frames_dir):
            return
        bundled_dir = safe_resource_path("Frames")
        if self.valid_frames(bundled_dir):
            shutil.copytree(bundled_dir, self.frames_dir, dirs_exist_ok=True)
            return
        bundled_zip = safe_resource_path("Frames.zip")
        if bundled_zip and bundled_zip.exists():
            try:
                _safe_extract_frames(bundled_zip, self.frames_dir)
            except Exception:
                pass

    def resolve(self) -> Path | None:
        cfg = self._read_config()
        custom = Path(cfg.get("custom_frames_path", "")) if cfg.get("custom_frames_path") else None
        if self.valid_frames(custom):
            return custom
        if self.valid_frames(self.frames_dir):
            return self.frames_dir
        bundled_dir = safe_resource_path("Frames")
        if self.valid_frames(bundled_dir):
            return bundled_dir
        return None

    def set_custom_path(self, path: Path | None) -> None:
        cfg = self._read_config()
        if path is None:
            cfg.pop("custom_frames_path", None)
        else:
            if not self.valid_frames(path):
                raise ValueError("That folder does not contain a valid NewFrames.json library.")
            cfg["custom_frames_path"] = str(path)
        self._write_config(cfg)

    def frame_count(self) -> int:
        p = self.resolve()
        return len([x for x in p.glob("*.png") if not x.name.startswith(".")]) if p else 0

    def download_latest(
        self,
        progress_cb: Callable[[float], None] | None = None,
        status_cb: Callable[[str], None] | None = None,
    ) -> Path:
        self.data_root.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(suffix=".zip", prefix="apple_frames_")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            if status_cb:
                status_cb("Connecting to MacStories CDN…")

            def report(block_num, block_size, total_size):
                if total_size > 0 and progress_cb:
                    progress_cb(min(100.0, block_num * block_size * 100.0 / total_size))

            try:
                urllib.request.urlretrieve(ASSETS_URL, tmp, reporthook=report)
            except urllib.error.URLError as exc:
                reason = getattr(exc, "reason", exc)
                if isinstance(reason, ssl.SSLError) or "certificate" in str(reason).lower():
                    # Windows often has curl.exe; use it as a TLS fallback.
                    curl = shutil.which("curl") or shutil.which("curl.exe")
                    if not curl:
                        raise
                    import subprocess
                    if status_cb:
                        status_cb("Python TLS failed; retrying with curl…")
                    subprocess.run([curl, "-L", "--fail", "-o", str(tmp), ASSETS_URL], check=True)
                else:
                    raise
            if status_cb:
                status_cb("Extracting and validating frame library…")
            _safe_extract_frames(tmp, self.frames_dir)
            if not self.valid_frames(self.frames_dir):
                raise ValueError("Downloaded frame library failed validation.")
            cfg = self._read_config()
            cfg.pop("custom_frames_path", None)
            self._write_config(cfg)
            if progress_cb:
                progress_cb(100.0)
            return self.frames_dir
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass


class AppleFramesEngine:
    def __init__(self, assets_dir: Path):
        self.assets_dir = Path(assets_dir)
        with open(self.assets_dir / "NewFrames.json", encoding="utf-8") as f:
            self.device_dict = json.load(f)
        self.device_index = self._build_device_index()
        self.device_names = sorted(self.device_index.keys())
        self.discovered_colors = self._discover_colors()

    def _build_device_index(self) -> dict[str, dict]:
        index: dict[str, dict] = {}
        for key, val in self.device_dict.items():
            if key == "variants" or not isinstance(val, dict):
                continue
            overlaps = val.get("overlap", {})
            if overlaps:
                for entry in overlaps.values():
                    if isinstance(entry, dict) and entry.get("name"):
                        index[entry["name"]] = entry
            elif val.get("name"):
                index[val["name"]] = val
        for name, entry in self.device_dict.get("variants", {}).items():
            index[name] = entry
        return index

    def _discover_colors(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        names_by_len = sorted(self.device_names, key=len, reverse=True)
        for png in self.assets_dir.glob("*.png"):
            stem = png.stem
            if stem.endswith("_mask"):
                continue
            owner = None
            for name in names_by_len:
                if stem == name or stem.startswith(name + " "):
                    owner = name
                    break
            if owner and stem != owner:
                suffix = stem[len(owner):].strip()
                if suffix:
                    result.setdefault(owner, []).append(suffix)
        for k in list(result):
            result[k] = sorted(set(result[k]))
        return result

    def detect_dimensions(self, width: int, height: int) -> tuple[dict | None, str | None]:
        entry = self.device_dict.get(str(width))
        if not isinstance(entry, dict):
            return None, None
        if "overlap" in entry:
            entry = entry.get("overlap", {}).get(str(height))
            if not isinstance(entry, dict):
                return None, None
        return entry, entry.get("name")

    def default_variant(self, primary_name: str) -> str:
        variants = FRAME_VARIANTS.get(primary_name)
        if not variants:
            return primary_name
        for name in variants:
            if name in self.device_index:
                return name
        return primary_name

    def variants_for(self, primary_name: str | None) -> list[str]:
        if not primary_name:
            return []
        values = FRAME_VARIANTS.get(primary_name, [primary_name])
        return [x for x in values if x in self.device_index]

    def colors_for(self, device_name: str) -> list[str]:
        ordered = FRAME_COLORS.get(device_name)
        discovered = self.discovered_colors.get(device_name, [])
        if ordered:
            valid = [c for c in ordered if (self.assets_dir / f"{device_name} {c}.png").exists()]
            extras = [c for c in discovered if c not in valid]
            return valid + extras
        return discovered

    def inspect(self, path: Path) -> dict:
        with Image.open(path) as im0:
            im = ImageOps.exif_transpose(im0)
            w, h = im.size
        entry, primary = self.detect_dimensions(w, h)
        if not entry or not primary:
            return {
                "path": Path(path), "width": w, "height": h, "supported": False,
                "primary": None, "device": None, "variants": [], "colors": []
            }
        device = self.default_variant(primary)
        return {
            "path": Path(path), "width": w, "height": h, "supported": True,
            "primary": primary, "device": device, "variants": self.variants_for(primary),
            "colors": self.colors_for(device),
        }

    def _resolve_color(self, device_name: str, color_choice: str | None) -> str | None:
        colors = self.colors_for(device_name)
        if not colors:
            return None
        choice = (color_choice or "Default").strip()
        if choice.lower() == "random":
            return random.choice(colors)
        if choice.lower() in ("", "default"):
            return colors[0]
        for c in colors:
            if c.lower() == choice.lower():
                return c
        return colors[0]

    def _load_frame(self, device_name: str, color: str | None) -> Image.Image:
        candidates = []
        if color:
            candidates.append(self.assets_dir / f"{device_name} {color}.png")
        candidates.append(self.assets_dir / f"{device_name}.png")
        for c in self.colors_for(device_name):
            candidates.append(self.assets_dir / f"{device_name} {c}.png")
        for p in candidates:
            if p.exists():
                with Image.open(p) as im:
                    return im.convert("RGBA")
        raise FileNotFoundError(f"Frame asset not found for {device_name}")

    @staticmethod
    def _target_orientation_from_size(size: tuple[int, int]) -> str:
        """Resolve the *real* orientation from screenshot pixels.

        Apple Frames asset filenames are not reliable enough to decide this:
        a few files named Landscape are physically stored portrait, and the
        reverse can also happen. Screenshot resolution is authoritative.
        """
        w, h = size
        return "landscape" if w > h else "portrait"

    @classmethod
    def _normalise_frame_orientation(
        cls, frame: Image.Image, device_name: str, x: int, y: int, screenshot_size: tuple[int, int]
    ) -> tuple[Image.Image, int, int, bool]:
        """Rotate a frame to match the screenshot's actual pixel orientation.

        The screenshot resolution decides portrait vs landscape; the asset's
        filename is only a label. This handles mislabeled/misstored frame PNGs
        in either direction and transforms the screen offsets with the canvas.
        """
        target = cls._target_orientation_from_size(screenshot_size)
        sw, sh = screenshot_size
        fw, fh = frame.size

        if target == "landscape" and fw < fh:
            # Stored portrait -> intended landscape.  ROTATE_90 is CCW.
            frame = frame.transpose(Image.Transpose.ROTATE_90)
            # Before rotation the corresponding screen is portrait (sh × sw).
            # CCW transform: (x, y, width=sh) -> (y, fw - x - sh).
            return frame, int(y), int(fw - x - sh), True

        if target == "portrait" and fw > fh:
            # Defensive inverse for any future incorrectly-oriented portrait asset.
            frame = frame.transpose(Image.Transpose.ROTATE_270)
            # Before rotation the corresponding screen is landscape (sh × sw).
            # CW transform: (x, y, height=sw) -> (fh - y - sw, x).
            return frame, int(fh - y - sw), int(x), True

        return frame, int(x), int(y), False

    @classmethod
    def _normalise_mask_orientation(
        cls, mask: Image.Image, device_name: str, screenshot_size: tuple[int, int]
    ) -> tuple[Image.Image, bool]:
        """Rotate masks to the screenshot's actual pixel orientation before resizing."""
        target = cls._target_orientation_from_size(screenshot_size)
        sw, sh = screenshot_size
        rotated = False

        # Exact swapped dimensions are common in AppleFrames401 for landscape
        # variants. Rotating preserves the rounded-corner/Dynamic Island shape.
        if mask.size == (sh, sw):
            if target == "landscape":
                mask = mask.transpose(Image.Transpose.ROTATE_90)
                rotated = True
            elif target == "portrait":
                mask = mask.transpose(Image.Transpose.ROTATE_270)
                rotated = True

        # Also fix obvious aspect-orientation mismatches even if a More Space
        # resolution means dimensions are not an exact swap.
        if not rotated and target == "landscape" and mask.width < mask.height:
            mask = mask.transpose(Image.Transpose.ROTATE_90)
            rotated = True
        elif not rotated and target == "portrait" and mask.width > mask.height:
            mask = mask.transpose(Image.Transpose.ROTATE_270)
            rotated = True

        if mask.size != (sw, sh):
            mask = mask.resize((sw, sh), RESAMPLE_LANCZOS)
        return mask, rotated

    def render(self, path: Path, device_name: str | None = None, color_choice: str | None = None) -> tuple[Image.Image, dict]:
        with Image.open(path) as opened:
            img = ImageOps.exif_transpose(opened).convert("RGBA")
            w, h = img.size
        detected_entry, primary = self.detect_dimensions(w, h)
        if device_name:
            entry = self.device_index.get(device_name)
            if not entry:
                raise ValueError(f"Unknown device frame: {device_name}")
            resolved = device_name
        else:
            if not detected_entry or not primary:
                raise ValueError(f"Unsupported screenshot resolution: {w}×{h}")
            resolved = self.default_variant(primary)
            entry = self.device_index.get(resolved, detected_entry)

        resize_width = entry.get("resizeWidth")
        if resize_width:
            resize_width = int(resize_width)
            ratio = resize_width / img.width
            img = img.resize((resize_width, max(1, round(img.height * ratio))), RESAMPLE_LANCZOS)

        color = self._resolve_color(resolved, color_choice)
        frame = self._load_frame(resolved, color)

        x, y = int(entry["x"]), int(entry["y"])
        frame, x, y, frame_orientation_fixed = self._normalise_frame_orientation(
            frame, resolved, x, y, img.size
        )

        mask_orientation_fixed = False
        if entry.get("mask") == "yes":
            mask_path = self.assets_dir / f"{resolved}_mask.png"
            if mask_path.exists():
                with Image.open(mask_path) as m:
                    mask = m.convert("RGBA")
                mask, mask_orientation_fixed = self._normalise_mask_orientation(mask, resolved, img.size)
                r, g, b, _ = img.split()
                mask_r = mask.split()[0]
                img = Image.merge("RGBA", (r, g, b, mask_r))

        # Fail clearly if bad metadata/asset geometry would clip the screenshot.
        if x < 0 or y < 0 or x + img.width > frame.width or y + img.height > frame.height:
            raise ValueError(
                f"Frame geometry mismatch for {resolved}: screenshot {img.width}×{img.height} "
                f"at ({x},{y}) does not fit frame {frame.width}×{frame.height}."
            )

        canvas = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        canvas.paste(img, (x, y), img)
        result = Image.alpha_composite(canvas, frame)
        return result, {
            "source": str(path), "device": resolved, "primary": primary,
            "color": color, "dimensions": f"{w}x{h}",
            "physicalHeight": float(entry.get("physicalHeight", 0) or 0),
            "resized": bool(resize_width),
            "frameOrientationFixed": frame_orientation_fixed,
            "maskOrientationFixed": mask_orientation_fixed,
        }

    @staticmethod
    def _scaled_for_composition(
        images: list[Image.Image], infos: list[dict], proportional: bool
    ) -> tuple[list[Image.Image], bool]:
        work = [im.copy().convert("RGBA") for im in images]
        physical = [float(info.get("physicalHeight", 0) or 0) for info in infos]
        do_scale = (
            proportional and len(work) > 1 and len(work) == len(physical)
            and all(v > 0 for v in physical)
            and len(set(round(v, 4) for v in physical)) > 1
        )
        if do_scale:
            px_per_mm = [im.height / ph for im, ph in zip(work, physical)]
            ref_ppm = min(px_per_mm)
            scaled = []
            for im, ph in zip(work, physical):
                target_h = max(1, round(ph * ref_ppm))
                scale = target_h / im.height
                if abs(scale - 1.0) > 0.001:
                    scaled.append(im.resize((max(1, round(im.width * scale)), target_h), RESAMPLE_LANCZOS))
                else:
                    scaled.append(im)
            work = scaled
        return work, do_scale

    @staticmethod
    def compose(
        images: list[Image.Image], infos: list[dict], spacing: int = 60,
        proportional: bool = True, background: str = "transparent",
        arrangement: str = "Grid", columns: int | None = None,
    ) -> Image.Image:
        """Compose framed screenshots as a grid, horizontal strip, or vertical stack.

        Proportional physical scaling is applied before layout, so mixed-device
        compositions retain realistic relative sizes regardless of arrangement.
        Grid mode uses variable row heights and column widths rather than forcing
        every cell to the same giant rectangle.
        """
        if not images:
            raise ValueError("No images to compose.")

        work, do_scale = AppleFramesEngine._scaled_for_composition(images, infos, proportional)
        spacing = max(0, int(spacing))
        if background.lower() == "transparent":
            bg = (0, 0, 0, 0)
        else:
            bg = background

        if len(work) == 1:
            return work[0]

        layout = (arrangement or "Grid").strip().lower()

        if layout == "horizontal":
            total_w = sum(im.width for im in work) + spacing * (len(work) - 1)
            max_h = max(im.height for im in work)
            result = Image.new("RGBA", (total_w, max_h), bg)
            x = 0
            for im in work:
                y = max_h - im.height if do_scale else (max_h - im.height) // 2
                result.alpha_composite(im, dest=(x, y))
                x += im.width + spacing
            return result

        if layout == "vertical":
            max_w = max(im.width for im in work)
            total_h = sum(im.height for im in work) + spacing * (len(work) - 1)
            result = Image.new("RGBA", (max_w, total_h), bg)
            y = 0
            for im in work:
                x = (max_w - im.width) // 2
                result.alpha_composite(im, dest=(x, y))
                y += im.height + spacing
            return result

        if layout != "grid":
            raise ValueError(f"Unknown composition arrangement: {arrangement}")

        count = len(work)
        if columns is None:
            cols = max(1, math.ceil(math.sqrt(count)))
        else:
            cols = max(1, min(count, int(columns)))
        rows = math.ceil(count / cols)

        col_widths = [0] * cols
        row_heights = [0] * rows
        for i, im in enumerate(work):
            r, c = divmod(i, cols)
            col_widths[c] = max(col_widths[c], im.width)
            row_heights[r] = max(row_heights[r], im.height)

        total_w = sum(col_widths) + spacing * max(0, cols - 1)
        total_h = sum(row_heights) + spacing * max(0, rows - 1)
        result = Image.new("RGBA", (total_w, total_h), bg)

        x_starts = []
        acc = 0
        for width in col_widths:
            x_starts.append(acc)
            acc += width + spacing
        y_starts = []
        acc = 0
        for height in row_heights:
            y_starts.append(acc)
            acc += height + spacing

        for i, im in enumerate(work):
            r, c = divmod(i, cols)
            x = x_starts[c] + (col_widths[c] - im.width) // 2
            # With physical scaling, align devices on a common baseline inside
            # each row; otherwise center them vertically in the row.
            if do_scale:
                y = y_starts[r] + row_heights[r] - im.height
            else:
                y = y_starts[r] + (row_heights[r] - im.height) // 2
            result.alpha_composite(im, dest=(x, y))
        return result

    @staticmethod
    def merge(
        images: list[Image.Image], infos: list[dict], spacing: int = 60,
        proportional: bool = True, background: str = "transparent"
    ) -> Image.Image:
        """Backward-compatible horizontal merge used by older callers."""
        return AppleFramesEngine.compose(
            images, infos, spacing, proportional, background, arrangement="Horizontal"
        )


def save_image(
    image: Image.Image,
    path: Path,
    fmt: str = "PNG",
    quality: int = 92,
    png_compress: int = 6,
    optimize: bool = True,
    progressive: bool = True,
) -> Path:
    fmt = fmt.upper()
    suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp", "TIFF": ".tif", "BMP": ".bmp", "PDF": ".pdf"}[fmt]
    path = Path(path).with_suffix(suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    kwargs = {}
    out = image
    if fmt in ("JPEG", "WEBP"):
        out = image.convert("RGB")
        kwargs["quality"] = max(1, min(100, int(quality)))
        if fmt == "JPEG":
            kwargs["optimize"] = bool(optimize)
            kwargs["progressive"] = bool(progressive)
        else:
            kwargs["method"] = 6
    elif fmt == "PNG":
        kwargs["compress_level"] = max(0, min(9, int(png_compress)))
        kwargs["optimize"] = bool(optimize)
    elif fmt == "PDF":
        out = image.convert("RGB")
        kwargs["resolution"] = 300
    out.save(path, format=fmt, **kwargs)
    return path


def rounded_rect_mask(size, radius):
    w, h = size
    radius = max(0, min(int(radius), min(w, h) // 2))
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    return mask


def fit_cover(im: Image.Image, target_size):
    tw, th = target_size
    sw, sh = im.size
    if tw <= 0 or th <= 0 or sw <= 0 or sh <= 0:
        raise ValueError("Invalid target/source size.")
    scale = max(tw / sw, th / sh)
    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    resized = im.resize((nw, nh), RESAMPLE_LANCZOS)
    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    return resized.crop((left, top, left + tw, top + th))


def apply_fill_scale(im: Image.Image, target_size, fill_scale_pct):
    pct = max(100.0, float(fill_scale_pct))
    if pct <= 100.0:
        return im
    tw, th = target_size
    scale = pct / 100.0
    nw, nh = max(1, round(tw * scale)), max(1, round(th * scale))
    bigger = im.resize((nw, nh), RESAMPLE_LANCZOS)
    left, top = max(0, (nw - tw) // 2), max(0, (nh - th) // 2)
    return bigger.crop((left, top, left + tw, top + th))


def parse_frame_filename(name: str):
    import re
    m = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", name)
    return tuple(int(x) for x in m.groups()) if m else None


def list_images(folder: Path, sort_mode: str = "Name") -> list[Path]:
    files = [p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_INPUTS]
    if sort_mode == "Modified time":
        files.sort(key=lambda p: (p.stat().st_mtime, p.name.lower()))
    else:
        files.sort(key=lambda p: p.name.lower())
    return files


def manual_grid_estimate(cfg: dict) -> dict:
    frame = Image.open(cfg["frame"]).convert("RGBA")
    portrait_size = frame.size
    landscape_size = frame.rotate(90, expand=True).size
    count = len(cfg["files"])
    cols = cfg.get("columns") or max(1, math.ceil(math.sqrt(count)))
    rows = math.ceil(count / cols)
    mode = cfg.get("orientation_mode", "Auto")
    grid_mode = cfg.get("grid_mode", "Tight")
    if mode == "Force landscape":
        cell_w, cell_h = landscape_size
    elif mode == "Force portrait":
        cell_w, cell_h = portrait_size
    else:
        cell_w = max(portrait_size[0], landscape_size[0])
        cell_h = max(portrait_size[1], landscape_size[1]) if grid_mode == "Uniform cell" else None
    if mode in ("Force landscape", "Force portrait") or grid_mode == "Uniform cell":
        total_w = cols * cell_w + max(0, cols - 1) * cfg["gap_x"]
        total_h = rows * cell_h + max(0, rows - 1) * cfg["gap_y"]
    else:
        row_h = max(portrait_size[1], landscape_size[1])
        total_w = cols * cell_w + max(0, cols - 1) * cfg["gap_x"]
        total_h = rows * row_h + max(0, rows - 1) * cfg["gap_y"]
    return {"width": total_w, "height": total_h, "ram_gb": total_w * total_h * 4 / (1024 ** 3), "count": count}


def build_manual_grid(
    cfg: dict,
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> tuple[Image.Image, dict]:
    base_frame = Image.open(cfg["frame"]).convert("RGBA")
    frame_portrait = base_frame
    frame_landscape = base_frame.rotate(90 if cfg.get("rotate_landscape", "Left (CCW)").startswith("Left") else -90, expand=True)
    portrait_size, landscape_size = frame_portrait.size, frame_landscape.size

    sw, sh = cfg["screen_w"], cfg["screen_h"]
    sx, sy = cfg["screen_x"], cfg["screen_y"]
    if sx + sw > portrait_size[0] or sy + sh > portrait_size[1]:
        raise ValueError("Portrait screen rectangle goes outside the frame image.")
    inset = cfg["inset"]
    x0, y0, x1, y1 = sx + inset, sy + inset, sx + sw - inset, sy + sh - inset
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Inset is too large for the screen rectangle.")
    screen_box_portrait = (x0, y0, x1, y1)
    pw, ph = portrait_size
    if cfg.get("rotate_landscape", "Left (CCW)").startswith("Left"):
        screen_box_landscape = (y0, pw - x1, y1, pw - x0)
    else:
        screen_box_landscape = (ph - y1, x0, ph - y0, x1)
    pw_box, ph_box = round(x1 - x0), round(y1 - y0)
    lw_box = round(screen_box_landscape[2] - screen_box_landscape[0])
    lh_box = round(screen_box_landscape[3] - screen_box_landscape[1])
    portrait_mask = rounded_rect_mask((pw_box, ph_box), cfg["corner_radius"])
    landscape_mask = rounded_rect_mask((lw_box, lh_box), cfg["corner_radius"])

    files = cfg["files"]
    count = len(files)
    cols = cfg.get("columns") or max(1, math.ceil(math.sqrt(count)))
    rows = math.ceil(count / cols)
    mode = cfg.get("orientation_mode", "Auto")
    grid_mode = cfg.get("grid_mode", "Tight")
    cell_w = max(portrait_size[0], landscape_size[0])
    cell_h = max(portrait_size[1], landscape_size[1]) if grid_mode == "Uniform cell" else None
    if mode == "Force landscape":
        cell_w, cell_h = landscape_size
    elif mode == "Force portrait":
        cell_w, cell_h = portrait_size

    def render_one(path: Path):
        with Image.open(path) as im0:
            im = ImageOps.exif_transpose(im0).convert("RGBA")
        is_landscape = im.width > im.height
        want_landscape = mode == "Force landscape" or (mode not in ("Force portrait",) and is_landscape)
        if mode == "Force portrait":
            want_landscape = False
        if want_landscape and im.height > im.width:
            im = im.rotate(-90, expand=True)
        elif not want_landscape and im.width > im.height:
            im = im.rotate(90, expand=True)
        if want_landscape:
            frame = frame_landscape.copy(); box = screen_box_landscape
            bw, bh = lw_box, lh_box; mask = landscape_mask; tile_size = landscape_size
        else:
            frame = frame_portrait.copy(); box = screen_box_portrait
            bw, bh = pw_box, ph_box; mask = portrait_mask; tile_size = portrait_size
        fitted = fit_cover(im, (bw, bh))
        fitted = apply_fill_scale(fitted, (bw, bh), cfg["fill_scale"])
        fitted.putalpha(mask)
        frame.alpha_composite(fitted, dest=(round(box[0]), round(box[1])))
        return path.name, frame, tile_size

    tiles = [None] * count
    workers = max(1, int(cfg.get("workers", os.cpu_count() or 1)))
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(render_one, p): i for i, p in enumerate(files)}
        for fut in as_completed(futures):
            if cancel_cb and cancel_cb():
                raise RuntimeError("Build cancelled.")
            idx = futures[fut]
            tiles[idx] = fut.result()
            done += 1
            if progress_cb:
                progress_cb(55 * done / count, f"Rendered {done}/{count}: {tiles[idx][0]}")

    if mode in ("Force landscape", "Force portrait") or grid_mode == "Uniform cell":
        row_heights = [cell_h] * rows
    else:
        row_heights = []
        for r in range(rows):
            start_i, end_i = r * cols, min(count, (r + 1) * cols)
            row_heights.append(max(tiles[i][2][1] for i in range(start_i, end_i)))
    total_w = cols * cell_w + max(0, cols - 1) * cfg["gap_x"]
    total_h = sum(row_heights) + max(0, rows - 1) * cfg["gap_y"]
    giant = Image.new("RGBA", (total_w, total_h), cfg["bg"])

    row_y, acc = [], 0
    for r, rh in enumerate(row_heights):
        row_y.append(acc)
        acc += rh + (cfg["gap_y"] if r < rows - 1 else 0)
    for i, tile_info in enumerate(tiles):
        if cancel_cb and cancel_cb():
            raise RuntimeError("Build cancelled.")
        _, tile, tile_size = tile_info
        row, col = i // cols, i % cols
        x = col * (cell_w + cfg["gap_x"])
        y = row_y[row]
        ox = x + (cell_w - tile_size[0]) // 2
        oy = y + (row_heights[row] - tile_size[1]) // 2
        giant.alpha_composite(tile, dest=(ox, oy))
        if progress_cb:
            progress_cb(55 + 30 * (i + 1) / count, f"Placed {i + 1}/{count} tiles")
    return giant, {"width": total_w, "height": total_h, "ram_gb": total_w * total_h * 4 / (1024 ** 3), "count": count}
