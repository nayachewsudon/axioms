import re
import json
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pathlib import Path
from pydantic import BaseModel
from app.weighted_metrics.matrix_calc import build_comparison_matrix
from app.weighted_metrics.llm_scorer import recommend_vendor
from app.services.report_generator import generate_report_pdf

router = APIRouter(prefix="/evaluate", tags=["evaluate"])

class EvaluateRequest(BaseModel):
    weighting_input_storage_path: str
    normalised_storage_paths: list[str]

def fix_path(path_str: str) -> Path:
    print(f"DEBUG fix_path input: {path_str}")
    path_str = re.sub(r'^.*?/storage/', '/app/storage/', path_str)
    print(f"DEBUG fix_path output: {path_str}")
    return Path(path_str)

@router.post("")
def evaluate(request: EvaluateRequest, export_pdf: bool = False):
    # Load weighting input (criteria + tradeoff answers)
    weighting_path = fix_path(request.weighting_input_storage_path)
    if not weighting_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weighting input file not found"
        )
    weighting_input = json.loads(weighting_path.read_text(encoding="utf-8"))
    criteria = weighting_input["criteria"]
    tradeoff_answers = weighting_input.get("tradeoff_answers", [])

    # Load each normalized quotation
    quotations = []
    for path_str in request.normalised_storage_paths:
        path = fix_path(path_str)
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Normalised quotation file not found: {path_str}"
            )
        quotation_file = json.loads(path.read_text(encoding="utf-8"))
        quotations.append(quotation_file["normalised"])

    # Build vendor list from quotations
    vendors = [{"name": q["vendor_name"], **q} for q in quotations]

    # Run the matrix
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
        print("recommendation keys:", recommendation.keys())
        print("recommendation:", recommendation)
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

@router.get("/debug")
def debug(path: str):
    fixed = fix_path(path)
    return {
        "original_path": path,
        "fixed_path": str(fixed),
        "exists": fixed.exists(),
        "app_storage_contents": list(Path("/app/storage").rglob("*")) if Path("/app/storage").exists() else "/app/storage does not exist",
        "app_app_storage_contents": list(Path("/app/app/storage").rglob("*")) if Path("/app/app/storage").exists() else "/app/app/storage does not exist",
    }