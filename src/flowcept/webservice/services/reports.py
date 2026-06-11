"""Workflow-card content helpers shared by workflow and campaign routers."""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

from flowcept.report.service import build_workflow_card, generate_report
from flowcept.webservice.services.serializers import normalize_docs


def workflow_card_response(
    format: str,
    workflow_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> Response:
    """Build a workflow card as a JSON or markdown HTTP response.

    Parameters
    ----------
    format : str
        ``"json"`` for the structured card content, ``"markdown"`` for the rendered card.
    workflow_id : str, optional
        Workflow scope (exactly one of workflow_id/campaign_id must be set).
    campaign_id : str, optional
        Campaign scope.

    Returns
    -------
    Response
        ``JSONResponse`` or markdown ``Response``.
    """
    if format not in ("json", "markdown"):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}. Use json or markdown.")

    scope = workflow_id or campaign_id
    try:
        if format == "json":
            card = build_workflow_card(workflow_id=workflow_id, campaign_id=campaign_id)
            content: Dict[str, Any] = normalize_docs(
                [
                    {
                        "dataset": card["dataset"],
                        "transformations": card["transformations"],
                        "object_summary": card["object_summary"],
                        "input_mode": card["input_mode"],
                    }
                ]
            )[0]
            return JSONResponse(content=content)

        fd, output_path = tempfile.mkstemp(prefix=f"workflow_card_{scope}_", suffix=".md")
        os.close(fd)
        try:
            generate_report(
                report_type="workflow_card",
                format="markdown",
                output_path=output_path,
                workflow_id=workflow_id,
                campaign_id=campaign_id,
            )
            with open(output_path, "rb") as handle:
                payload = handle.read()
        finally:
            try:
                os.remove(output_path)
            except Exception:
                pass
        return Response(content=payload, media_type="text/markdown; charset=utf-8")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate workflow card: {exc}") from exc
