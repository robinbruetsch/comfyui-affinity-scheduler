"""Reorders ready nodes so expensive models are swapped as rarely as possible.

ComfyUI's ExecutionList.ux_friendly_pick_node favours nodes that are at most
two hops from an output. In a workflow that generates one image and then edits
it in several independent branches, that makes each branch run to completion
before the next one starts:

    PE -> TE -> sampler -> PE -> TE -> sampler -> PE -> TE -> sampler

Every arrow is a model swap. When the models do not all fit in system RAM at
once - MiniMax H3-Image needs ~21 GB for the DiT and ~27 GB for the text
encoder in int8, against 32 GB of RAM - each swap is a reload from disk, which
on a hard drive costs minutes.

This picks, among the nodes that are already ready, prompt-expander work first,
then text-encoder work, and only then everything else:

    PE -> PE -> PE -> TE -> TE -> TE -> sampler -> sampler -> sampler

It only ever chooses from get_ready_nodes(), whose inputs are all computed, so
any choice is a valid topological order and the outputs are bit-identical.
Only the execution order changes.

Disable with COMFY_AFFINITY_SCHEDULER=0. The log lines that count model swaps
stay active either way, so both orders can be compared on the same workflow.
Remove this folder to uninstall.
"""

import logging
import os

from comfy_execution import graph

ENABLED = os.environ.get("COMFY_AFFINITY_SCHEDULER", "1") != "0"

PROMPT_EXPANDERS = {"TextGenerate", "TextGenerateV2"}
SAMPLERS = {
    "KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced",
    "ClownsharKSampler_Beta", "ClownsharkChainsampler_Beta",
}

# Keep the true original on the class: loading this module twice would
# otherwise capture the already-patched method and recurse forever.
_original_pick = getattr(graph.ExecutionList, "_affinity_original_pick", graph.ExecutionList.ux_friendly_pick_node)
graph.ExecutionList._affinity_original_pick = _original_pick


def _category(execution_list, node_id):
    class_type = execution_list.dynprompt.get_node(node_id)["class_type"]
    if class_type in PROMPT_EXPANDERS:
        return "expander"
    # Conditioning/TextEncode nodes run the text encoder. A few cheap helpers
    # also match (ConditioningZeroOut, ...); preferring them costs nothing.
    if "Conditioning" in class_type or "TextEncode" in class_type:
        return "encoder"
    if class_type in SAMPLERS:
        return "sampler"
    return None


def _pick(self, node_list):
    chosen = None
    if ENABLED:
        for wanted in ("expander", "encoder"):
            chosen = next((n for n in node_list if _category(self, n) == wanted), None)
            if chosen is not None:
                break
    if chosen is None:
        chosen = _original_pick(self, node_list)

    category = _category(self, chosen)
    if category is not None:
        last = getattr(self, "_affinity_last", None)
        if last is not None and last != category:
            self._affinity_swaps = getattr(self, "_affinity_swaps", 0) + 1
            logging.info("[affinity] model swap #%d: %s -> %s (%s)", self._affinity_swaps, last, category, chosen)
        self._affinity_last = category
    return chosen


graph.ExecutionList.ux_friendly_pick_node = _pick
logging.info("[affinity] scheduler %s", "enabled" if ENABLED else "disabled (COMFY_AFFINITY_SCHEDULER=0), logging only")

NODE_CLASS_MAPPINGS = {}
