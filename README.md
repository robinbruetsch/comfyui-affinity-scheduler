# comfyui-affinity-scheduler

A tiny ComfyUI custom node (no nodes, no dependencies) that reorders **ready** nodes so expensive models are swapped as rarely as possible.

## Problem

ComfyUI picks the next node by how close it is to an output. In a workflow that generates one image and then edits it in several independent branches, each branch runs to completion before the next starts:

    expander -> encoder -> sampler -> expander -> encoder -> sampler -> ...

Every arrow is a model swap. If the models do not fit in system RAM together, each swap is a reload from disk.

## What it does

Among the nodes that are already ready, it prefers prompt-expander work first, then text-encoder work, then everything else:

    expander -> expander -> expander -> encoder -> encoder -> encoder -> sampler -> sampler -> sampler

It only chooses from nodes whose inputs are already computed, so every order is a valid topological order and outputs are bit-identical. Only the execution order changes.

Nodes are recognised by class name:

- expander: `TextGenerate`, `TextGenerateV2`
- encoder: class names containing `Conditioning` or `TextEncode`
- sampler: `KSampler`, `KSamplerAdvanced`, `SamplerCustom`, `SamplerCustomAdvanced`, ...

Unknown nodes keep ComfyUI's default order. On workflows without independent branches it changes nothing.

## Install

Copy this folder to `ComfyUI/custom_nodes/comfyui-affinity-scheduler` and restart. The log shows `[affinity] scheduler enabled` and `[affinity] model swap #N: a -> b (node)` lines.

Disable with the environment variable `COMFY_AFFINITY_SCHEDULER=0` (swap logging stays on, so you can compare both orders). Remove the folder to uninstall.

## Measured (one workflow, one machine)

RTX 2080 Ti 11 GB, 32 GB RAM, ComfyUI 0.45.2, MiniMax H3-Image carousel workflow (1 generation + 3 edits, 6 prompt expanders):

- model swaps: 10 with the default order, 4 with the scheduler
- saved time: about 1 minute on NVMe. On a hard drive the reloads cost far more.

Only tested on this workflow.

## Related findings from the same setup

- **`--reserve-vram 3` slowed a 9.75 GB int8 prompt expander from ~5.5 to ~1.3 tokens/s.** With more reserve the model no longer fits in usable VRAM, and ComfyUI streams weights from disk for every token (`fast_disk`). With `--reserve-vram 1.5` the same model ran at ~5.5 tokens/s (200 tokens in 36 s, model already loaded). A low reserve can still cause driver-side offloading during large sampling steps, so check your own workload.
- **`asym_w4a8_int8` weights are slow on Turing (sm75).** comfy_kitchen's fast CUDA W4A8 kernels are gated to newer GPUs, so the eager fallback runs: ~11 ms for one 12288x4096 layer instead of well under 1 ms, ~1.25 tokens/s for the expander. On a 2080 Ti the int8 convrot variant is the better choice.

## License

GPL-3.0, like ComfyUI.
