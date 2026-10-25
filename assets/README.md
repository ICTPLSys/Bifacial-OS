# Architecture figure

| File | Purpose |
| --- | --- |
| [architecture.drawio](architecture.drawio) | Editable source; open with draw.io / diagrams.net |
| [architecture.svg](architecture.svg) | Vector image embedded in the root README |
| [architecture.pdf](architecture.pdf) | Vector PDF for review and sharing |

The figure shows component responsibilities and control relationships. The Resource Manager is inside the Agent Execution Service. This repository contains part of the framework code; the MCP server and resource manager code are pending open-source release. The root README describes the current release scope.

Edit the `.drawio` file and regenerate both exports together. Use a white background, a light theme, a small border, and crop to the diagram. Labels use plain text so the SVG does not depend on HTML rendering. Export commands with draw.io Desktop are:

```bash
drawio --export --format svg --theme light --border 18 --embed-svg-fonts false --output assets/architecture.svg assets/architecture.drawio
drawio --export --format pdf --theme light --crop --border 18 --output assets/architecture.pdf assets/architecture.drawio
```

Run these commands from the repository root; on Linux without a display, prefix each command with `xvfb-run -a`. The exports were generated with draw.io 32.5.5. Check text and arrow placement after editing.
