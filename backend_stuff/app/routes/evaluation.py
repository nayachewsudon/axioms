import json
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from app.weighted_metrics.matrix_calc import build_comparison_matrix
from app.weighted_metrics.llm_scorer import recommend_vendor
from app.services.report_generator import generate_report_pdf

router = APIRouter(prefix="/evaluate", tags=["evaluate"])

class EvaluateRequest(BaseModel):
    weighting_input: dict
    normalised_storage_paths: list[dict]

@router.post("")
def evaluate(request: EvaluateRequest, export_pdf: bool = False):
    criteria = request.weighting_input["criteria"]
    tradeoff_answers = request.weighting_input.get("tradeoff_answers", [])

    quotations = [q["normalised"] for q in request.normalised_storage_paths]
    vendors = [{"name": q["vendor_name"], **q} for q in quotations]

    try:
        matrix = build_comparison_matrix(
            vendors=vendors,
            criteria=criteria,
            quotations=quotations,
            tradeoff_answers=tradeoff_answers
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc)
        ) from exc

    rankings = matrix.reset_index().to_dict(orient="records")
    recommendation = recommend_vendor(rankings, criteria)

    if export_pdf:
        pdf_bytes = generate_report_pdf(
            product="Vendor Evaluation",
            rankings=rankings,
            recommendation=recommendation,
            criteria=criteria
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=axiom_evaluation_report.pdf"}
        )

    return {
        "status": "success",
        "rankings": rankings,
        "recommendation": recommendation
    }