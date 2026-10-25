"""Render the midterm demo video and stills from one finished pipeline run.

Read-only: replays the recorded P1-global fusion from existing SLAM/depth
artifacts (no model, SLAM or GT in the map path), checks that the replayed map
equals the recorded map.npz exactly, and renders frames with NumPy/Pillow.
GT depth is read only for the panels labelled "evaluation only". Needs FFmpeg
on PATH for the MP4. Never overwrites an existing output file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rt_mapping.alignment.correspondences import prediction_grid  # noqa: E402
from rt_mapping.contracts.geometry import load_prediction  # noqa: E402
from rt_mapping.fusion import VoxelFusion, depth_points, metric_pose  # noqa: E402

W, H = 1280, 720
BG = (15, 20, 25)
FG = (235, 238, 240)
MUTED = (150, 160, 170)
ACCENT = (255, 168, 38)
TEAL = (64, 196, 180)
DEPTH_RANGE_M = (0.5, 3.5)
ERROR_MAX_M = 0.5
FPS = 30
HOLD = 3  # video frames per input frame: 10 input frames per second of video
TURBO = None
YAW, DISTANCE, HEIGHT, FOCAL = -20.0, 2.9, 0.7, 0.42  # virtual viewer around the map median


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def turbo(values, low, high):
    global TURBO
    if TURBO is None:
        from matplotlib import colormaps
        TURBO = (colormaps["turbo"](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)
    index = np.clip((values - low) / (high - low), 0, 1)
    out = TURBO[np.nan_to_num(index * 255).astype(int)]
    out[~np.isfinite(values)] = (40, 40, 40)
    return out


def magma(values, high):
    from matplotlib import colormaps
    lut = (colormaps["magma"](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)
    out = lut[np.nan_to_num(np.clip(values / high, 0, 1) * 255).astype(int)]
    out[~np.isfinite(values)] = (40, 40, 40)
    return out


class Fonts:
    def __init__(self, path):
        self.path = path

    def __call__(self, size, bold=False):
        candidates = [self.path] if self.path else []
        candidates += ["C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
                       "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
                       else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return ImageFont.truetype(candidate, size)
        return ImageFont.load_default()


def load_sources(run_dir, sequence_dir, manifest_path):
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if run["status"] != "ok":
        raise SystemExit(f"source run status is {run['status']}, expected ok")
    rid = run["run_id"]
    stages = run_dir / "stages"
    slam, geometry, comparison = (stages / f"{rid}.{name}" for name in ("slam", "geometry", "comparison"))
    for stage in (slam, geometry, comparison):
        if json.loads((stage / "run.json").read_text(encoding="utf-8"))["status"] != "ok":
            raise SystemExit(f"stage {stage.name} is not ok")
    methods = comparison / "methods"
    global_dir, oracle_dir = methods / f"{rid}.comparison.global", methods / f"{rid}.comparison.oracle"
    with np.load(slam / "sparse/keyframes.npz", allow_pickle=False) as archive:
        cameras = dict(archive)
    with np.load(slam / "sparse/landmarks.npz", allow_pickle=False) as archive:
        landmarks = dict(archive)
    alignment = json.loads((global_dir / "alignment.json").read_text(encoding="utf-8"))
    mapping = json.loads((global_dir / "run.json").read_text(encoding="utf-8"))["config"]
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    frames = manifest["splits"][run["dataset"]["split"]]["frames"]
    online = np.loadtxt(slam / "input_setup/trajectory/trajectory_online.txt")
    geometry_run = json.loads((geometry / "run.json").read_text(encoding="utf-8"))
    hashes = {str(p.relative_to(run_dir)).replace("\\", "/"): sha256(p) for p in (
        run_dir / "run.json", slam / "run.json", geometry / "run.json", comparison / "run.json",
        slam / "sparse/keyframes.npz", slam / "sparse/landmarks.npz", global_dir / "alignment.json",
        global_dir / "map.npz", oracle_dir / "map.npz")}
    return dict(run=run, slam=slam, geometry=geometry, global_dir=global_dir, oracle_dir=oracle_dir,
                cameras=cameras, landmarks=landmarks, scale=float(alignment["scale"]), mapping=mapping,
                frames=frames, online=online, sequence_dir=Path(sequence_dir), hashes=hashes,
                process_res=geometry_run["config"]["model"]["process_res"], model=geometry_run["model"]["repo"])


def rgb_image(src, frame, size=None):
    image = Image.open(src["sequence_dir"] / frame["rgb_path"]).convert("RGB")
    return image if size is None else image.resize(size, Image.BILINEAR)


def gt_depth_on_grid(src, frame, shape):
    raw = np.asarray(Image.open(src["sequence_dir"] / frame["depth_path"]), dtype=np.float64) / 5000.0
    h, w = shape
    rows = np.floor((np.arange(h) + 0.5) * raw.shape[0] / h).astype(int)
    cols = np.floor((np.arange(w) + 0.5) * raw.shape[1] / w).astype(int)
    depth = raw[rows][:, cols]
    depth[depth <= 0] = np.nan
    return depth


def replay_fusion(src):
    """Recorded P1-global loop (mapping_run.run_mapping) plus per-voxel RGB for display."""
    config, cameras = src["mapping"], src["cameras"]
    fusion = VoxelFusion(config["voxel_size_m"], config["max_voxels"])
    keys_all, colors_all, states = [], [], []
    for index in np.argsort(cameras["timestamp_s"])[::config["keyframe_interval"]]:
        frame_id = int(cameras["frame_id"][index])
        prediction = load_prediction(src["geometry"] / "predictions" / f"frame_{frame_id:06d}.npz")
        _, grid = prediction_grid(prediction, cameras["K"][index], cameras["image_size_wh"][index])
        distortion = cameras["distortion"][index] if grid == "raw_distorted" else None
        points = depth_points(prediction, metric_pose(cameras["T_wc"][index], src["scale"]),
                              distortion=distortion, min_depth_m=config["min_depth_m"],
                              max_depth_m=config["max_depth_m"], confidence_threshold=config["confidence_threshold"],
                              pixel_stride=config["pixel_stride"])
        fusion.add(points)
        # same mask/order as depth_points, to attach the keyframe's RGB to each point (display only)
        mask = prediction.valid_mask & (prediction.depth_m >= config["min_depth_m"]) & (prediction.depth_m <= config["max_depth_m"])
        sampled = np.zeros_like(mask)
        sampled[::config["pixel_stride"], ::config["pixel_stride"]] = True
        v, u = np.nonzero(mask & sampled)
        h, w = prediction.depth_m.shape
        rgb = np.asarray(rgb_image(src, src["frames"][frame_id], (w, h)), dtype=np.float64)
        keys_all.append(np.floor(points / fusion.voxel_size_m).astype(np.int64))
        colors_all.append(rgb[v, u])
        xyz, _ = fusion.cloud(config["min_voxel_observations"])
        keys, inverse = np.unique(np.concatenate(keys_all), axis=0, return_inverse=True)
        sums = np.zeros((len(keys), 3))
        np.add.at(sums, inverse.ravel(), np.concatenate(colors_all))
        counts = np.bincount(inverse.ravel(), minlength=len(keys))[:, None]
        if len(keys) != len(xyz):
            raise SystemExit("colour voxel keys disagree with VoxelFusion")
        states.append(dict(frame_id=frame_id, xyz=xyz, rgb=(sums / counts).astype(np.uint8),
                           T_wc=metric_pose(cameras["T_wc"][index], src["scale"])))
    with np.load(src["global_dir"] / "map.npz", allow_pickle=False) as recorded:
        if not np.array_equal(recorded["xyz_m"], states[-1]["xyz"]):
            raise SystemExit("replayed map differs from recorded map.npz")
    return states


def look_at(eye, target):
    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, -1.0, 0.0]))
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    return np.stack([right, down, forward]), eye


def splat(points, colors, view, size, focal, radius=2, background=BG):
    rotation, eye = view
    w, h = size
    camera = (points - eye) @ rotation.T
    keep = camera[:, 2] > 0.05
    camera, colors = camera[keep], colors[keep]
    u = np.round(focal * camera[:, 0] / camera[:, 2] + w / 2).astype(int)
    v = np.round(focal * camera[:, 1] / camera[:, 2] + h / 2).astype(int)
    image = np.empty((h, w, 3), np.uint8)
    image[:] = background
    zbuffer = np.full(h * w, np.inf)
    shade = np.clip(1.15 - 0.12 * (camera[:, 2] - camera[:, 2].min()), 0.55, 1.0)[:, None]
    colors = (colors * shade).astype(np.uint8)
    for dy in range(radius):
        for dx in range(radius):
            uu, vv = u + dx, v + dy
            inside = (uu >= 0) & (uu < w) & (vv >= 0) & (vv < h)
            flat = vv[inside] * w + uu[inside]
            np.minimum.at(zbuffer, flat, camera[inside, 2])
    for dy in range(radius):
        for dx in range(radius):
            uu, vv = u + dx, v + dy
            inside = (uu >= 0) & (uu < w) & (vv >= 0) & (vv < h)
            flat = vv[inside] * w + uu[inside]
            front = camera[inside, 2] <= zbuffer[flat] + 1e-9
            image.reshape(-1, 3)[flat[front]] = colors[inside][front]
    return image


def project(points, view, size, focal):
    rotation, eye = view
    camera = (np.atleast_2d(points) - eye) @ rotation.T
    return np.column_stack((focal * camera[:, 0] / camera[:, 2] + size[0] / 2,
                            focal * camera[:, 1] / camera[:, 2] + size[1] / 2)), camera[:, 2]


def orbit_view(center, yaw_deg, distance, height):
    yaw = np.radians(yaw_deg)
    eye = center + np.array([distance * np.sin(yaw), -height, -distance * np.cos(yaw)])
    return look_at(eye, center.copy())


def draw_cameras(image, poses, view, size, focal, color, current=None):
    draw = ImageDraw.Draw(image)
    centres = np.array([pose[:3, 3] for pose in poses])
    if len(centres):
        uv, z = project(centres, view, size, focal)
        valid = z > 0.05
        if valid.sum() > 1:
            draw.line([tuple(p) for p in uv[valid]], fill=color, width=2)
        for p in uv[valid]:
            draw.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=color)
    if current is not None:
        uv, z = project(current[:3, 3], view, size, focal)
        if z[0] > 0.05:
            p = uv[0]
            draw.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], outline=FG, width=2)


def text(draw, xy, value, font, fill=FG, anchor="la"):
    draw.text(xy, value, font=font, fill=fill, anchor=anchor)


def badge(draw, xy, value, font, fill, color=BG):
    box = draw.textbbox(xy, value, font=font)
    draw.rounded_rectangle([box[0] - 8, box[1] - 5, box[2] + 8, box[3] + 5], radius=6, fill=fill)
    draw.text(xy, value, font=font, fill=color)


def fit(image, box):
    w, h = box
    scale = min(w / image.width, h / image.height)
    return image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)


class Demo:
    def __init__(self, src, states, fonts):
        self.src, self.states, self.f = src, states, fonts
        final = states[-1]["xyz"]
        cameras = np.array([s["T_wc"][:3, 3] for s in states])
        self.center = 0.75 * np.median(final, axis=0) + 0.25 * cameras.mean(axis=0)
        self.keyframe_ids = [s["frame_id"] for s in states]
        timestamps = np.array([f["rgb_timestamp_s"] for f in src["frames"]])
        online = src["online"]
        nearest = np.abs(online[:, 0][:, None] - timestamps[None, :]).argmin(axis=1)
        self.online_frame = {int(n): online[i] for i, n in enumerate(nearest)
                             if abs(online[i, 0] - timestamps[n]) < 1e-3}
        self.landmarks = src["landmarks"]["xyz_slam"] * src["scale"]
        self.map_cache = {}

    def state_at(self, frame_id):
        done = [s for s in self.states if s["frame_id"] <= frame_id]
        return len(done), done

    def map_panel(self, count, size, yaw=YAW):
        key = (count, size, yaw)
        if key not in self.map_cache:
            focal = size[0] * FOCAL
            view = orbit_view(self.center, yaw, DISTANCE, HEIGHT)
            if count:
                state = self.states[count - 1]
                image = Image.fromarray(splat(state["xyz"], state["rgb"], view, size, focal, radius=2))
                draw_cameras(image, [s["T_wc"] for s in self.states[:count]], view, size, focal, ACCENT,
                             current=self.states[count - 1]["T_wc"])
            else:
                image = Image.new("RGB", size, BG)
            self.map_cache[key] = image
        return self.map_cache[key].copy()

    def slam_panel(self, frame_id, count, size, yaw=YAW):
        """Same virtual camera as the map panel; landmarks and poses scaled by the recorded scale."""
        focal = size[0] * FOCAL
        view = orbit_view(self.center, yaw, DISTANCE, HEIGHT)
        image = Image.fromarray(splat(self.landmarks, np.full((len(self.landmarks), 3), 200, np.uint8),
                                      view, size, focal, radius=3))
        draw = ImageDraw.Draw(image)
        path = [self.online_frame[i][1:4] * self.src["scale"] for i in range(frame_id + 1) if i in self.online_frame]
        if len(path) > 1:
            uv, _ = project(np.array(path), view, size, focal)
            draw.line([tuple(p) for p in uv], fill=TEAL, width=3)
        draw_cameras(image, [s["T_wc"] for s in self.states[:count]], view, size, focal, ACCENT)
        if path:
            uv, _ = project(path[-1], view, size, focal)
            p = uv[0]
            draw.ellipse([p[0] - 7, p[1] - 7, p[0] + 7, p[1] + 7], outline=FG, width=2)
        return image

    def composite(self, frame_id):
        f, src = self.f, self.src
        canvas = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(canvas)
        frame = src["frames"][frame_id]
        count, _ = self.state_at(frame_id)
        is_keyframe = frame_id in self.keyframe_ids
        cell = (632, 292)
        origins = [(8, 52), (640, 52), (8, 392), (640, 392)]
        titles = ["RGB input (monocular)",
                  f"Metric depth: DA3METRIC-LARGE (process_res {src['process_res']})",
                  "pySLAM: trajectory + sparse landmarks",
                  "Dense map (recorded P1-global fusion)"]
        text(draw, (16, 14), "TUM RGB-D fr1/xyz smoke, 200 frames", f(22, True))
        text(draw, (W - 16, 14), f"frame {frame_id:03d} / 199", f(22, True), anchor="ra")
        for (x, y), title in zip(origins, titles):
            text(draw, (x + 4, y - 4), title, f(17, True), MUTED)
        rgb = fit(rgb_image(src, frame), (cell[0], cell[1] - 24))
        canvas.paste(rgb, (origins[0][0] + (cell[0] - rgb.width) // 2, origins[0][1] + 20))
        prediction = load_prediction(src["geometry"] / "predictions" / f"frame_{frame_id:06d}.npz")
        depth = np.where(prediction.valid_mask, prediction.depth_m, np.nan)
        depth_img = fit(Image.fromarray(turbo(depth, *DEPTH_RANGE_M)), (cell[0] - 70, cell[1] - 24))
        dx = origins[1][0] + 4
        canvas.paste(depth_img, (dx, origins[1][1] + 20))
        bar = Image.fromarray(turbo(np.linspace(DEPTH_RANGE_M[1], DEPTH_RANGE_M[0], depth_img.height)[:, None].repeat(14, 1), *DEPTH_RANGE_M))
        bx = dx + depth_img.width + 10
        canvas.paste(bar, (bx, origins[1][1] + 20))
        for value in (0.5, 1.5, 2.5, 3.5):
            yy = origins[1][1] + 20 + (DEPTH_RANGE_M[1] - value) / (DEPTH_RANGE_M[1] - DEPTH_RANGE_M[0]) * (depth_img.height - 1)
            text(draw, (bx + 20, yy), f"{value:.1f} m", f(15), FG, "lm")
        canvas.paste(self.slam_panel(frame_id, count, (cell[0], cell[1] - 24)), (origins[2][0], origins[2][1] + 20))
        canvas.paste(self.map_panel(count, (cell[0], cell[1] - 24)), (origins[3][0], origins[3][1] + 20))
        # overlays in the panel title rows, never over the content
        right2, right3 = origins[2][0] + cell[0] - 4, origins[3][0] + cell[0] - 4
        pose = "online pose" if frame_id in self.online_frame else "no online pose"
        text(draw, (right2, origins[2][1] - 4), f"{pose} | keyframes {count}/{len(self.states)}", f(17), FG, "ra")
        if is_keyframe:
            badge(draw, (origins[2][0] + 14, origins[2][1] + 30), "NEW KEYFRAME", f(17, True), ACCENT)
        xyz = self.states[count - 1]["xyz"] if count else np.empty((0, 3))
        text(draw, (right3, origins[3][1] - 4), f"{len(xyz):,} voxels (2 cm)".replace(",", " "), f(17, True), FG, "ra")
        self.footer(draw)
        return canvas

    def footer(self, draw):
        run = self.src["run"]
        text(draw, (16, H - 12), f"Offline research prototype. Rendered offline from run {run['run_id']} "
             f"(commit {run['git_commit'][:7]}). Playback speed is not processing speed.", self.f(16), MUTED, "ld")

    def rotation_frame(self, yaw):
        f, final = self.f, self.states[-1]
        size = (W, H - 90)
        focal = W * 0.52
        view = orbit_view(self.center, yaw, DISTANCE, HEIGHT)
        image = Image.fromarray(splat(final["xyz"], final["rgb"], view, size, focal, radius=3))
        draw_cameras(image, [s["T_wc"] for s in self.states], view, size, focal, ACCENT)
        canvas = Image.new("RGB", (W, H), BG)
        canvas.paste(image, (0, 50))
        draw = ImageDraw.Draw(canvas)
        voxels = f"{len(final['xyz']):,}".replace(",", " ")
        text(draw, (16, 14), f"Final dense metric map (P1-global): {voxels} voxels, {len(self.states)} keyframes",
             f(22, True))
        text(draw, (W - 16, 14), "orange: keyframe cameras", f(18), ACCENT, "ra")
        self.footer(draw)
        return canvas

    def intro(self):
        canvas = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(canvas)
        run = self.src["run"]
        text(draw, (W // 2, 270), "RGB  →  depth + SLAM  →  dense 3D map", self.f(46, True), FG, "mm")
        text(draw, (W // 2, 345), "TUM RGB-D fr1/xyz, first 200 frames (smoke split)", self.f(26), FG, "mm")
        text(draw, (W // 2, 390), f"DA3METRIC-LARGE (process_res {self.src['process_res']}) + pySLAM monocular, "
             "global scale alignment, voxel fusion", self.f(22), MUTED, "mm")
        text(draw, (W // 2, 450), "Offline research prototype. Rendered offline; not real-time.", self.f(24, True), ACCENT, "mm")
        text(draw, (W // 2, 500), f"Source: {run['run_id']}, commit {run['git_commit'][:7]}, status ok",
             self.f(18), MUTED, "mm")
        return canvas


def sparse_dense_oracle(demo, src, fonts):
    with np.load(src["oracle_dir"] / "map.npz", allow_pickle=False) as archive:
        oracle = archive["xyz_m"]
    final = demo.states[-1]
    size = (600, 470)
    focal = size[0] * 0.8  # tighter than the video panels: three side-by-side maps
    view = orbit_view(demo.center, YAW, DISTANCE, HEIGHT)
    grey = lambda n: np.full((n, 3), 205, np.uint8)  # noqa: E731
    panels = [("B0 sparse SLAM landmarks", demo.landmarks, grey(len(demo.landmarks)), 4),
              ("P1-global: SLAM poses + DA3 depth", final["xyz"], final["rgb"], 2),
              ("B1 oracle: SLAM poses + GT depth", oracle, grey(len(oracle)), 2)]
    canvas = Image.new("RGB", (1860, 600), BG)
    draw = ImageDraw.Draw(canvas)
    for i, (title, xyz, rgb, radius) in enumerate(panels):
        image = Image.fromarray(splat(xyz, rgb, view, size, focal, radius=radius))
        canvas.paste(image, (20 + i * 615, 70))
        text(draw, (20 + i * 615 + 300, 30), title, fonts(28, True), FG, "mm")
        text(draw, (20 + i * 615 + 300, 570), f"{len(xyz):,} points".replace(",", " ")
             + ("  (B1 = labelled oracle)" if i == 2 else ""), fonts(22), MUTED, "mm")
    return canvas


def depth_panels(src, frame_ids, fonts, title, zoom=1.4):
    rows = []
    for frame_id in frame_ids:
        frame = src["frames"][frame_id]
        prediction = load_prediction(src["geometry"] / "predictions" / f"frame_{frame_id:06d}.npz")
        depth = np.where(prediction.valid_mask, prediction.depth_m, np.nan)
        gt = gt_depth_on_grid(src, frame, depth.shape)
        error = np.abs(depth - gt)
        size = (depth.shape[1] * zoom, depth.shape[0] * zoom)
        size = (int(size[0]), int(size[1]))
        tiles = [rgb_image(src, frame, size), Image.fromarray(turbo(depth, *DEPTH_RANGE_M)).resize(size, Image.NEAREST),
                 Image.fromarray(turbo(gt, *DEPTH_RANGE_M)).resize(size, Image.NEAREST),
                 Image.fromarray(magma(error, ERROR_MAX_M)).resize(size, Image.NEAREST)]
        valid = np.isfinite(error)
        rows.append((frame_id, tiles, float(np.mean(error[valid] / gt[valid]))))
    tw, th = rows[0][1][0].size
    canvas = Image.new("RGB", (40 + 4 * (tw + 20), 110 + len(rows) * (th + 50)), BG)
    draw = ImageDraw.Draw(canvas)
    text(draw, (20, 20), title, fonts(28, True), FG)
    heads = ["RGB input", "DA3 predicted depth", "GT depth (evaluation only)", "|pred - GT| (evaluation only)"]
    for i, head in enumerate(heads):
        text(draw, (20 + i * (tw + 20) + tw // 2, 80), head, fonts(22, True), MUTED, "mm")
    for r, (frame_id, tiles, absrel) in enumerate(rows):
        y = 100 + r * (th + 50)
        for i, tile in enumerate(tiles):
            canvas.paste(tile, (20 + i * (tw + 20), y))
        text(draw, (20, y + th + 8), f"frame {frame_id}: AbsRel {absrel:.3f} on this display grid "
             f"(colour scales: depth {DEPTH_RANGE_M[0]}-{DEPTH_RANGE_M[1]} m, error 0-{ERROR_MAX_M} m)",
             fonts(20), MUTED)
    return canvas


def save(image, path, written):
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    image.save(path, optimize=True)
    written.append(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="finished pipeline run directory")
    parser.add_argument("--sequence-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True, help="new directory for PNG video frames")
    parser.add_argument("--font", default=None, help="TTF with Latin glyphs (default Arial / DejaVu)")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--failure-frames", type=int, nargs="+", default=[80, 72, 84])
    parser.add_argument("--depth-frame", type=int, default=100)
    args = parser.parse_args(argv)

    fonts = Fonts(args.font)
    src = load_sources(args.run, args.sequence_dir, args.manifest)
    states = replay_fusion(src)
    print(f"replayed {len(states)} keyframes; map equals recorded map.npz ({len(states[-1]['xyz'])} voxels)")
    demo = Demo(src, states, fonts)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=False)
    written = []

    index = 0

    def emit(image, repeat=1):
        nonlocal index
        for _ in range(repeat):
            image.save(args.work_dir / f"f{index:05d}.png")
            index += 1

    emit(demo.intro(), int(2.0 * FPS))
    for frame_id in range(len(src["frames"])):
        emit(demo.composite(frame_id), HOLD)
    last = demo.composite(len(src["frames"]) - 1)
    emit(last, int(1.0 * FPS))
    rotation = int(8 * FPS)
    for i in range(rotation):
        emit(demo.rotation_frame(YAW + 35.0 * np.sin(2 * np.pi * i / rotation)))

    video = args.output_dir / "mapping_demo.mp4"
    if video.exists():
        raise SystemExit(f"refusing to overwrite {video}")
    subprocess.run([args.ffmpeg, "-loglevel", "error", "-framerate", str(FPS), "-i", str(args.work_dir / "f%05d.png"),
                    "-c:v", "libx264", "-preset", "slow", "-crf", "30", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", "-an", str(video)], check=True)
    written.append(video)

    save(demo.composite(len(src["frames"]) - 1), args.output_dir / "mapping_demo_thumbnail.png", written)
    save(demo.rotation_frame(YAW), args.output_dir / "final_dense_map.png", written)
    save(sparse_dense_oracle(demo, src, fonts), args.output_dir / "sparse_dense_oracle.png", written)
    save(depth_panels(src, [args.depth_frame], fonts, f"Frame {args.depth_frame}: DA3 metric depth vs TUM GT depth"),
         args.output_dir / "depth_comparison.png", written)
    save(depth_panels(src, args.failure_frames, fonts,
                      "Worst map-contribution keyframes (U-01): local depth errors on person, monitor edges, far background", zoom=1.0),
         args.output_dir / "failure_analysis.png", written)

    record = {"source_run": src["run"]["run_id"], "source_commit": src["run"]["git_commit"],
              "source_status": src["run"]["status"], "model": src["model"], "process_res": src["process_res"],
              "scale": src["scale"], "keyframes": [s["frame_id"] for s in states],
              "map_voxels": len(states[-1]["xyz"]), "replay_equals_recorded_map_npz": True,
              "video": {"fps": FPS, "frames": index, "duration_s": index / FPS, "size": [W, H]},
              "depth_colour_range_m": list(DEPTH_RANGE_M), "error_colour_max_m": ERROR_MAX_M,
              "source_sha256": src["hashes"],
              "outputs_sha256": {p.name: sha256(p) for p in written},
              "gt_use": "GT depth only in depth_comparison.png and failure_analysis.png panels labelled evaluation only",
              "scope": "offline rendering of finished artifacts; no model, SLAM or fusion re-execution"}
    manifest = args.output_dir / "demo_provenance.json"
    if manifest.exists():
        raise SystemExit(f"refusing to overwrite {manifest}")
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("map_voxels", "video", "outputs_sha256")}, indent=2))


if __name__ == "__main__":
    main()
