from __future__ import annotations

import json
import re

BUNDLE_RE = re.compile(r"===BUNDLE-BEGIN===\s*(.*?)\s*===BUNDLE-END===", re.DOTALL)


class BundleExtractionError(RuntimeError):
    pass


def extract_bundle(text: str) -> dict:
    m = BUNDLE_RE.search(text)
    if not m:
        raise BundleExtractionError(
            f"Could not find ===BUNDLE-BEGIN===/===BUNDLE-END=== delimiters in agent output:\n{text[:2000]}"
        )
    blob = m.group(1).strip()
    if blob.startswith("```"):
        blob = re.sub(r"^```(?:json)?\s*", "", blob)
        blob = re.sub(r"\s*```$", "", blob)
    try:
        bundle = json.loads(blob)
    except json.JSONDecodeError as e:
        raise BundleExtractionError(f"Bundle was not valid JSON: {e}\nPayload:\n{blob[:2000]}") from e

    # Normalize prompt_recommendations: convert list to string
    # Some agents may emit [] or ["rec1", "rec2"] instead of a string
    if "prompt_recommendations" in bundle:
        recs = bundle["prompt_recommendations"]
        if isinstance(recs, list):
            if not recs:
                bundle["prompt_recommendations"] = ""
            else:
                # Convert list of recommendations to bullet-point string
                bundle["prompt_recommendations"] = "\n".join(
                    rec if rec.startswith("-") else f"- {rec}" for rec in recs
                )

    return bundle
