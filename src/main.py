# DEPRECATED — Use mandate_finder.api.main instead.
# This app is kept for backward compatibility but will be removed.
# All routes have been consolidated into src/mandate_finder/api/main.py.

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database import Base, engine, get_session
from src.models.ab_test import ABTest, ABTestVariant, Campaign, MessageEvent, MessageVariant
from src.services.ab_test_service import ABTestService
from src.workers.reply_detector import ReplyDetector

app = FastAPI(title="Mandate Finder - A/B Testing & Reply Detection")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(engine)


class VariantCreate(BaseModel):
    name: str
    subject: str | None = None
    body: str
    call_to_action: str | None = None
    personalization_level: str = "low"
    channel: str = "email"
    is_control: bool = False


class ABTestCreate(BaseModel):
    name: str
    campaign_id: str
    metric: str = "reply_rate"
    variant_ids: list[str]


class SendGridWebhookPayload(BaseModel):
    event: str
    email: str
    campaign_id: str
    timestamp: float | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/campaigns")
def create_campaign(name: str, industry: str | None = None, db: Session = Depends(get_session)):
    campaign = Campaign(name=name, industry=industry)
    db.add(campaign)
    db.commit()
    return {"id": campaign.id, "name": campaign.name}


@app.post("/campaigns/{campaign_id}/variants")
def create_variant(campaign_id: str, variant: VariantCreate, db: Session = Depends(get_session)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    v = MessageVariant(campaign_id=campaign_id, **variant.model_dump())
    db.add(v)
    db.commit()
    return {"id": v.id, "name": v.name}


@app.post("/ab-tests")
def create_ab_test(test: ABTestCreate, db: Session = Depends(get_session)):
    t = ABTest(campaign_id=test.campaign_id, name=test.name, metric=test.metric)
    db.add(t)
    db.flush()

    for vid in test.variant_ids:
        av = ABTestVariant(ab_test_id=t.id, variant_id=vid)
        db.add(av)
    db.commit()
    return {"id": t.id, "name": t.name}


@app.get("/ab-tests/{test_id}/performance")
def get_performance(test_id: str, db: Session = Depends(get_session)):
    test = db.query(ABTest).filter(ABTest.id == test_id).first()
    if not test:
        raise HTTPException(404, "ABTest not found")

    service = ABTestService(db)
    results = [service.get_variant_performance(av.variant) for av in test.variants]

    chi_result = service.run_chi_squared_opens(test)
    mw_result = service.run_mann_whitney_reply(test)

    return {
        "test_id": test.id,
        "test_name": test.name,
        "status": test.status,
        "winning_variant_id": test.winning_variant_id,
        "variants": results,
        "chi_squared_opens": {"p_value": chi_result["p_value"], "significant": chi_result["significant"]},
        "mann_whitney_reply": {"p_value": mw_result["p_value"], "significant": mw_result["significant"]},
    }


@app.post("/ab-tests/{test_id}/promote")
def promote_winner(test_id: str, db: Session = Depends(get_session)):
    test = db.query(ABTest).filter(ABTest.id == test_id).first()
    if not test:
        raise HTTPException(404, "ABTest not found")

    service = ABTestService(db)
    result = service.auto_promote(test)

    if not result:
        return {"promoted": False, "reason": "Not yet significant or insufficient data"}
    return {"promoted": True, "winning_variant_id": result.winning_variant_id}


@app.post("/sendgrid-webhook")
def sendgrid_webhook(payload: SendGridWebhookPayload, background_tasks: BackgroundTasks, db: Session = Depends(get_session)):
    detector = ReplyDetector(db)
    result = detector.handle_sendgrid_webhook(payload.model_dump())
    return result


@app.get("/optimal-send-time/{persona_key}")
def get_optimal_time(persona_key: str, db: Session = Depends(get_session)):
    service = ABTestService(db)
    return service.get_optimal_send_time(persona_key)


@app.get("/ab-tests/{test_id}/report")
def export_report(test_id: str, db: Session = Depends(get_session)):
    test = db.query(ABTest).filter(ABTest.id == test_id).first()
    if not test:
        raise HTTPException(404, "ABTest not found")

    service = ABTestService(db)
    variants = [service.get_variant_performance(av.variant) for av in test.variants]

    chi = service.run_chi_squared_opens(test)
    mw = service.run_mann_whitney_reply(test)

    return {
        "test_name": test.name,
        "status": test.status,
        "total_variants": len(variants),
        "n": sum(v["sent"] for v in variants),
        "variants": [
            {
                "name": v["variant_name"],
                "n": v["sent"],
                "open_rate": v["open_rate"],
                "reply_rate": v["reply_rate"],
                "meeting_rate": v["meeting_rate"],
            }
            for v in variants
        ],
        "chi_squared_p_value": chi["p_value"],
        "mann_whitney_p_value": mw["p_value"],
    }
