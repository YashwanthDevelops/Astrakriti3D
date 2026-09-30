# Research visuals for the demo video

These are 1920 × 1080 PNG overlays, ready to place over the research and implementation section of the demo.

## Suggested order

1. [**01-technology-landscape.png**](01-technology-landscape.png) — show while introducing the approaches reviewed. It separates photogrammetry, Gaussian splatting, and world-model systems by their output and validation limits.
2. [**02-selector-experiment.png**](02-selector-experiment.png) — show while explaining what Astrakriti3D tested. The aggressive run used fewer frames and less recorded processing time, but had much larger camera-to-input-GPS residuals and fragmented coverage. The chart says these are single runs and not independent accuracy measurements.
3. [**03-current-output-evidence.png**](03-current-output-evidence.png) — show when introducing the working project output. It uses a real viewer screenshot and includes the current review's coverage and accuracy caveats.

## Evidence-aligned voiceover

> We reviewed several ways to turn captured imagery into 3D. They make different trade-offs: photogrammetry estimates geometry, Gaussian splatting focuses on realistic views, and newer world models also generate scene content. For our current workflow, we use WebODM with traceable video and telemetry preparation. In our own selector experiments, cutting frames did not guarantee a better reconstruction, so we kept the conservative baseline. The current run produces a real 3D output, while coverage and independent accuracy checks remain open work.

## Sources and caveats

- Technology landscape: [technology assessment](../../../output/pdf/Astrakriti3D_Drone_Video_to_3D_Technology_Assessment_2026-09.pdf), sections 7–8.1 and reference IDs shown in the image.
- Primary references: [COLMAP reconstruction tutorial](https://colmap.github.io/tutorial), [OpenDroneMap outputs](https://docs.opendronemap.org/outputs/), [3D Gaussian Splatting paper](https://doi.org/10.1145/3592433), and [World Labs Atlas announcement](https://www.worldlabs.ai/blog/atlas).
- Selector comparison: [phase 19 report](../../../evidence/phase19/lightweight-20260915-v4/comparison_report.json), [phase 18 report](../../../evidence/phase18/coverage-aware-20260915-v14/comparison_report.json), and [phase 16 report](../../../evidence/phase16/aggressive-webodm-20260915/comparison_report.json).
- Current output: [quality review](../../../runs/DJI_0142-R1-demo-20260929-193104/quality-review.md) and [report metrics](../../../runs/DJI_0142-R1-demo-20260929-193104/report-metrics.json).
- The attached reference chart's model names and values were not reused as Astrakriti3D results. This project did not run a same-input benchmark against the external reconstruction products or model families shown in that image.
- Selector experiments used the same WebODM backend with different frame-selection inputs. There was one recorded run per configuration. GPS residuals compare camera estimates to input telemetry, not to independent surveyed checkpoints.
- The latest demo output is visibly patchy and should not be described as complete or survey-validated.

## Regenerate

From the repository root, run:

```powershell
python demo/scripts/generate_research_visuals.py
```

The script reads existing JSON reports and the actual viewer screenshot, then writes the three PNGs and `visual-provenance.json` here.
