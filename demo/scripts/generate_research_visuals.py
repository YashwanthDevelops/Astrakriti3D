"""Generate evidence-backed, 16:9 research visuals for the Astrakriti3D demo.

Inputs are existing project reports. The script does not alter source evidence.
Run from the repository root with: python demo/scripts/generate_research_visuals.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "demo" / "assets" / "research-stats"

BG = "#F5F7FB"
CARD = "#FFFFFF"
INK = "#172B4D"
MUTED = "#64728A"
GRID = "#DCE3ED"
BLUE = "#5969B3"
TEAL = "#278B82"
GOLD = "#B7812F"
CORAL = "#BC5D55"
PALE_BLUE = "#E9ECF8"
PALE_RED = "#F8EAE8"


def read_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def new_slide(title: str, subtitle: str, eyebrow: str):
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=BG)
    fig.text(0.055, 0.954, eyebrow.upper(), color=BLUE, fontsize=10,
             weight="bold", va="top")
    fig.text(0.055, 0.908, title, color=INK, fontsize=26,
             weight="bold", va="top")
    fig.text(0.055, 0.855, subtitle, color=MUTED, fontsize=12.2, va="top")
    return fig


def add_round_card(fig, x, y, w, h, face=CARD, edge=GRID, radius=0.018, lw=0.9):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.012,rounding_size={radius}",
        transform=fig.transFigure,
        facecolor=face,
        edgecolor=edge,
        linewidth=lw,
        zorder=0,
    )
    fig.add_artist(patch)
    return patch


def save_slide(fig, name: str, description: str):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=120, facecolor=BG, edgecolor="none")
    plt.close(fig)
    with Image.open(path) as rendered:
        rendered.convert("RGB").save(path, format="PNG", dpi=(120, 120), optimize=True)
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "pixels": [1920, 1080],
        "alt_text": description,
    }


def technology_landscape() -> dict:
    fig = new_slide(
        "Different 3D approaches solve different problems",
        "A single error score cannot fairly rank methods with different outputs and validation targets.",
        "Research comparison  /  technology landscape  /  reviewed 23 Sep 2026",
    )

    cards = [
        {
            "x": 0.055,
            "color": BLUE,
            "index": "01",
            "label": "PHOTO-TO-GEOMETRY",
            "title": "SfM + Multi-View Stereo",
            "systems": "WebODM / ODM  ·  COLMAP",
            "body": (
                "Estimates camera poses and 3D\ngeometry from overlapping images.",
                "Needs useful texture, overlap and\nvaried viewpoints. More frames can\nadd processing time.",
            ),
            "fit": "Astrakriti3D reconstruction backend",
            "sources": "Sources [04], [05]",
        },
        {
            "x": 0.36,
            "color": TEAL,
            "index": "02",
            "label": "FAST VIEW SYNTHESIS",
            "title": "Gaussian Splatting",
            "systems": "Polycam  ·  selected mapping products",
            "body": (
                "Produces visually rich, fast novel\nviews of a captured scene.",
                "Visual quality does not prove a\nsurvey-ready surface. Surface\nextraction and geometric QA are\nseparate steps.",
            ),
            "fit": "Useful representation; separate QA required",
            "sources": "Sources [10], [19]–[21]",
        },
        {
            "x": 0.665,
            "color": GOLD,
            "index": "03",
            "label": "WORLD-MODEL SYSTEMS",
            "title": "Atlas (early access)",
            "systems": "World Labs announcement reviewed 01 Sep 2026",
            "body": (
                "Describes multimodal scene\nreconstruction and generation.",
                "Reviewed release does not establish\ngeodetic control or inspection QA.",
            ),
            "fit": "Adjacent research; not our implemented engine",
            "sources": "Source [18]",
        },
    ]

    for item in cards:
        x, y, w, h = item["x"], 0.255, 0.28, 0.51
        add_round_card(fig, x, y, w, h)
        fig.add_artist(FancyBboxPatch(
            (x + 0.018, y + h - 0.014), w - 0.036, 0.009,
            boxstyle="round,pad=0.001,rounding_size=0.004",
            transform=fig.transFigure, facecolor=item["color"],
            edgecolor="none", zorder=2,
        ))
        fig.text(x + 0.025, y + h - 0.055, item["label"],
                 color=item["color"], fontsize=9.4, weight="bold", va="top")
        fig.text(x + 0.025, y + h - 0.105, item["title"],
                 color=INK, fontsize=17, weight="bold", va="top")
        fig.text(x + 0.025, y + h - 0.155, item["systems"],
                 color=MUTED, fontsize=9.2, va="top", wrap=True)
        fig.text(x + 0.025, y + h - 0.225, "WHAT IT DOES",
                 color=MUTED, fontsize=8.4, weight="bold", va="top")
        fig.text(x + 0.025, y + h - 0.258, item["body"][0],
                 color=INK, fontsize=10.0, va="top", linespacing=1.33)
        fig.text(x + 0.025, y + h - 0.34, "LIMIT TO KEEP IN VIEW",
                 color=MUTED, fontsize=8.4, weight="bold", va="top")
        fig.text(x + 0.025, y + h - 0.373, item["body"][1],
                 color=INK, fontsize=9.8, va="top", linespacing=1.3)
        fig.text(x + 0.025, y + 0.024, item["sources"],
                 color=MUTED, fontsize=8.6, va="bottom")

    add_round_card(fig, 0.055, 0.105, 0.89, 0.09, face=PALE_BLUE, edge="none", radius=0.012)
    fig.text(0.077, 0.163, "OUR IMPLEMENTATION", color=BLUE,
             fontsize=9.2, weight="bold", va="center")
    fig.text(0.077, 0.128,
             "Traceable video + DJI SRT preparation around WebODM / NodeODM. No same-input benchmark against these alternatives has been run.",
             color=INK, fontsize=11.1, va="center")
    fig.text(0.055, 0.054,
             "Source: Drone Video-to-3D Technology Assessment, v1.0 (23 Sep 2026), §§7–8.1 and refs [04], [05], [10], [18]–[21]. Product statements are attributed to publishers; this is a role comparison, not a performance ranking.",
             color=MUTED, fontsize=7.5, va="bottom")

    return save_slide(
        fig,
        "01-technology-landscape.png",
        "Three technology cards compare SfM/MVS, Gaussian splatting and early-access world models by purpose and limitation. A footer says Astrakriti3D uses WebODM/NodeODM and has not run a same-input comparison against the alternatives.",
    )


def load_experiment_rows() -> tuple[list[dict], list[str]]:
    phase19_path = "evidence/phase19/lightweight-20260915-v4/comparison_report.json"
    phase16_path = "evidence/phase16/aggressive-webodm-20260915/comparison_report.json"
    report = read_json(phase19_path)
    aggressive_report = read_json(phase16_path)
    raw = [
        ("R1 baseline", report["runs"]["R1"], BLUE),
        ("Lightweight coverage-aware", report["runs"]["lightweight_223"], TEAL),
        ("Coverage-aware", report["runs"]["coverage_aware_276"], GOLD),
    ]
    aggressive = aggressive_report["aggressive"]
    aggressive_residuals = aggressive["coordinate_residuals_meters"]
    raw.append(("Aggressive adaptive", {
        "input_frame_count": aggressive["input_frame_count"],
        "registered_images": aggressive["registered_image_count"],
        "processing_time_ms": aggressive["processing_time_ms"],
        "reprojection_error_pixels": aggressive["reprojection"]["reprojection_error_pixels"],
        "camera_gps_residuals_m": {
            "median_m": aggressive_residuals["median_meters"],
            "p95_m": aggressive_residuals["p95_meters"],
        },
    }, CORAL))

    rows = []
    for name, item, color in raw:
        residuals = item["camera_gps_residuals_m"]
        rows.append({
            "name": name,
            "frames": item["input_frame_count"],
            "registered": item["registered_images"],
            "minutes": item["processing_time_ms"] / 60000,
            "median_m": residuals["median_m"],
            "p95_m": residuals["p95_m"],
            "reprojection_px": item["reprojection_error_pixels"],
            "color": color,
        })
    sources = [phase19_path, "evidence/phase18/coverage-aware-20260915-v14/comparison_report.json", phase16_path]
    return rows, sources


def selector_comparison() -> tuple[dict, dict]:
    rows, sources = load_experiment_rows()
    fig = new_slide(
        "Fewer frames did not mean a better reconstruction",
        "Four WebODM runs on the same 193.6-second DJI capture · one recorded run per configuration · 15 Sep 2026",
        "Project experiment  /  frame-selection comparison",
    )

    fig.text(0.205, 0.782, "INPUT FRAMES", color=MUTED, fontsize=9,
             weight="bold", ha="center")
    fig.text(0.475, 0.782, "WEBODM PROCESSING TIME", color=MUTED,
             fontsize=9, weight="bold", ha="center")
    fig.text(0.78, 0.782, "CAMERA-TO-INPUT GPS RESIDUAL (m)", color=MUTED,
             fontsize=9, weight="bold", ha="center")

    ymin, ymax = -0.62, 3.62
    y = [3, 2, 1, 0]
    ax_frames = fig.add_axes([0.15, 0.27, 0.17, 0.47], facecolor="none")
    ax_time = fig.add_axes([0.39, 0.27, 0.17, 0.47], facecolor="none")
    ax_residual = fig.add_axes([0.66, 0.27, 0.27, 0.47], facecolor="none")

    for ax in (ax_frames, ax_time, ax_residual):
        ax.set_ylim(ymin, ymax)
        ax.set_yticks(y)
        ax.set_yticklabels([])
        ax.tick_params(axis="y", length=0)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(axis="x", colors=MUTED, labelsize=8, length=0, pad=6)
        ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)

    ax_frames.barh(y, [r["frames"] for r in rows], color=[r["color"] for r in rows], height=0.47, zorder=3)
    ax_frames.set_xlim(0, 315)
    ax_frames.set_xticks([0, 100, 200, 300])
    for yy, r in zip(y, rows):
        ax_frames.text(r["frames"] + 6, yy, str(r["frames"]), color=INK,
                       fontsize=9.3, weight="bold", va="center")

    ax_time.barh(y, [r["minutes"] for r in rows], color=[r["color"] for r in rows], height=0.47, zorder=3)
    ax_time.set_xlim(0, 36)
    ax_time.set_xticks([0, 10, 20, 30])
    for yy, r in zip(y, rows):
        ax_time.text(r["minutes"] + 0.7, yy, f"{r['minutes']:.1f} min", color=INK,
                     fontsize=9.1, weight="bold", va="center")

    ax_residual.set_xlim(0, 80)
    ax_residual.set_xticks([0, 20, 40, 60, 80])
    for yy, r in zip(y, rows):
        ax_residual.plot([r["median_m"], r["p95_m"]], [yy, yy], color=r["color"],
                         linewidth=3.2, solid_capstyle="round", zorder=3)
        ax_residual.scatter([r["median_m"]], [yy], marker="o", s=38,
                            color=r["color"], edgecolor="white", linewidth=0.7, zorder=4)
        ax_residual.scatter([r["p95_m"]], [yy], marker="^", s=43,
                            color=r["color"], edgecolor="white", linewidth=0.7, zorder=4)
        label_x = min(r["p95_m"] + 1.8, 77.7)
        ax_residual.text(label_x, yy, f"{r['median_m']:.2f}  /  {r['p95_m']:.2f}",
                         color=INK, fontsize=8.2, weight="bold", va="center")

    for yy, r in zip(y, rows):
        frac = (yy - ymin) / (ymax - ymin)
        fig_y = 0.27 + 0.47 * frac
        fig.text(0.055, fig_y + 0.012, r["name"], color=INK,
                 fontsize=9.8, weight="bold", va="center")
        fig.text(0.055, fig_y - 0.014, f"{r['registered']}/{r['frames']} registered",
                 color=MUTED, fontsize=8.1, va="center")

    fig.text(0.675, 0.235, "● Median     ▲ P95", color=MUTED, fontsize=8.2, va="center")

    add_round_card(fig, 0.055, 0.105, 0.89, 0.087, face=PALE_RED, edge="none", radius=0.012)
    fig.text(0.077, 0.161, "WHY AGGRESSIVE WAS NOT PROMOTED", color=CORAL,
             fontsize=9.1, weight="bold", va="center")
    fig.text(0.077, 0.126,
             "24% fewer frames and 35.6% shorter recorded runtime, but 74.91 m P95 GPS residual and visibly fragmented coverage. R1 stays the production baseline.",
             color=INK, fontsize=10.3, va="center")
    fig.text(0.055, 0.054,
             "Residuals compare reconstructed camera positions with input GPS; they are not independent survey accuracy. Single runs only; hardware and timing boundaries were not fully controlled. Sources: Phase 19 / Phase 18 / Phase 16 comparison reports.",
             color=MUTED, fontsize=7.5, va="bottom")

    alt = (
        "Horizontal comparison of four WebODM runs on one DJI capture. R1 used 194 frames in 28.1 minutes with 0.37 m median and 0.94 m P95 camera-to-input-GPS residual. Lightweight coverage-aware used 223 frames in 26.6 minutes with 0.96/2.27 m residuals. Coverage-aware used 276 frames in 32.3 minutes with 0.93/2.28 m residuals. Aggressive adaptive used 147 frames in 18.1 minutes with 43.78/74.91 m residuals and fragmented coverage. The caption says residuals are not surveyed accuracy and R1 remains the baseline."
    )
    asset = save_slide(fig, "02-selector-experiment.png", alt)
    data = {
        "file": asset["file"],
        "alt_text": alt,
        "raw_values": [
            {k: round(v, 6) if isinstance(v, float) else v for k, v in r.items() if k != "color"}
            for r in rows
        ],
        "transformations": ["processing_time_ms divided by 60000 to display minutes", "camera-to-input-GPS median and P95 drawn on a shared linear 0–80 m axis"],
        "source_files": sources,
        "caveat": "One run per configuration; residuals are against input telemetry, not independent surveyed checkpoints.",
    }
    return asset, data


def current_output_card() -> tuple[dict, dict]:
    run = "runs/DJI_0142-R1-demo-20260929-193104"
    metrics = read_json(f"{run}/report-metrics.json")
    img_path = ROOT / run / "screenshots" / "model-textured.png"
    model_img = Image.open(img_path).convert("RGB")
    fig = new_slide(
        "A real output is the start of validation, not the end",
        "Completed Astrakriti3D demo run · DJI_0142 · 29 Sep 2026 · ODX 3.8.4",
        "Implementation evidence  /  actual project output",
    )

    add_round_card(fig, 0.055, 0.235, 0.48, 0.535, face="#10191D", edge="#10191D", radius=0.014)
    ax = fig.add_axes([0.065, 0.252, 0.46, 0.50])
    ax.imshow(model_img)
    ax.axis("off")
    fig.text(0.075, 0.215, "Actual textured-model viewer capture · run output", color=MUTED,
             fontsize=8.6, va="center")

    stats = [
        ("194 / 194", "source images reconstructed", BLUE),
        (f"{metrics['processing']['dense_points'] / 1_000_000:.2f}M", "dense point-cloud points", TEAL),
        ("9,712 × 8,500", "orthophoto raster pixels", GOLD),
        ("≈ 5 cm / px", "verified raster spacing", CORAL),
    ]
    positions = [(0.565, 0.535), (0.765, 0.535), (0.565, 0.30), (0.765, 0.30)]
    for (value, label, color), (x, y) in zip(stats, positions):
        add_round_card(fig, x, y, 0.18, 0.205, face=CARD, edge=GRID, radius=0.014)
        fig.text(x + 0.016, y + 0.145, value, color=color, fontsize=17.5,
                 weight="bold", va="center")
        fig.text(x + 0.016, y + 0.073, label, color=MUTED, fontsize=9.0,
                 va="center", wrap=True)

    add_round_card(fig, 0.055, 0.105, 0.89, 0.082, face=PALE_RED, edge="none", radius=0.012)
    fig.text(0.077, 0.158, "QUALITY REVIEW", color=CORAL,
             fontsize=9.0, weight="bold", va="center")
    fig.text(0.077, 0.126,
             "The model is visibly patchy with incomplete coverage. SRT alignment and software GPS estimates were not checked against independent survey points.",
             color=INK, fontsize=10.5, va="center")
    fig.text(0.055, 0.054,
             "Sources: current run quality-review.md and report-metrics.json. The 5 cm/pixel figure describes raster sampling, not absolute positional accuracy. Screenshot is from the actual Astrakriti3D viewer.",
             color=MUTED, fontsize=7.5, va="bottom")

    alt = (
        "Evidence card with an actual screenshot of the completed Astrakriti3D textured-model viewer. Four metrics show 194 of 194 images reconstructed, 2.16 million dense points, a 9,712 by 8,500 pixel orthophoto and approximately 5 centimetres per pixel raster spacing. A visible caveat says coverage is patchy and there are no independent survey checkpoints."
    )
    asset = save_slide(fig, "03-current-output-evidence.png", alt)
    data = {
        "file": asset["file"],
        "alt_text": alt,
        "source_files": [
            f"{run}/quality-review.md",
            f"{run}/report-metrics.json",
            f"{run}/screenshots/model-textured.png",
        ],
        "metrics": {
            "reconstructed_images": metrics["processing"]["reconstructed_images"],
            "available_images": metrics["processing"]["available_shots"],
            "dense_points": metrics["processing"]["dense_points"],
            "orthophoto_pixels": [9712, 8500],
            "orthophoto_spacing_cm_per_pixel": 5,
        },
        "caveat": "Run review found patchy, incomplete coverage; no independent survey checkpoints; raster sampling is not positional accuracy.",
    }
    return asset, data


def main() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "savefig.transparent": False,
    })
    OUT.mkdir(parents=True, exist_ok=True)

    assets = [technology_landscape()]
    selector_asset, selector_data = selector_comparison()
    assets.append(selector_asset)
    output_asset, output_data = current_output_card()
    assets.append(output_asset)

    manifest = {
        "title": "Astrakriti3D research and demo visuals",
        "created_by": "demo/scripts/generate_research_visuals.py",
        "canvas": {"width": 1920, "height": 1080, "background": BG},
        "assets": assets,
        "selector_comparison": selector_data,
        "current_output": output_data,
        "technology_landscape_sources": [
            "output/pdf/Astrakriti3D_Drone_Video_to_3D_Technology_Assessment_2026-09.pdf, §§7–8.1, references [04], [05], [10], [18]–[21]"
        ],
        "integrity_note": "The attached reference chart's model names and values were not reused as project results. No cross-product performance benchmark is claimed.",
    }
    (OUT / "visual-provenance.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Created {len(assets)} 1920x1080 PNG visuals in {OUT}")


if __name__ == "__main__":
    main()
