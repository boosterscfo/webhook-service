import importlib
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import verify_webhook_token
from lib.slack import SlackNotifier

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_JOBS = {
    "cash_mgmt": ["banktransactionUpload"],
    "upload_financial_db": ["upload_financial_db"],
    "global_boosta": ["update_route"],
    "meta_ads_manager": [
        "update_ads",
        "add_ad",
        "regis_slack_send",
        "unregis_slack_send",
        "unregis_user_slack_send",
        "regis_user_slack_send",
    ],
}


def execute_job(job_name: str, function_name: str, payload: dict):
    if job_name not in ALLOWED_JOBS:
        raise ValueError(f"Unknown job: {job_name}")
    if function_name not in ALLOWED_JOBS[job_name]:
        raise ValueError(f"Unknown function: {job_name}.{function_name}")

    module = importlib.import_module(f"jobs.{job_name}")
    func = getattr(module, function_name)
    return func(payload)


@router.post("/webhook")
async def handle_webhook(
    payload: dict,
    _: None = Depends(verify_webhook_token),
):
    job = payload.get("job")
    function = payload.get("function")

    if not job or not function:
        raise HTTPException(
            status_code=400, detail="'job' and 'function' are required"
        )

    try:
        logger.info(f"Executing {job}.{function}")
        result = execute_job(job, function, payload)
        logger.info(f"Completed {job}.{function}")
        return {"status": "ok", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in {job}.{function}: {e}\n{traceback.format_exc()}")
        try:
            SlackNotifier.notify(
                text="Webhook Error",
                header=f"*[Webhook Error]* `{job}.{function}` 실행 중 에러 발생",
                body=f"```{str(e)}```",
                channel_id="C04FQ47F231",
            )
        except Exception:
            logger.error("Failed to send Slack error notification")
        raise HTTPException(status_code=500, detail=str(e))
