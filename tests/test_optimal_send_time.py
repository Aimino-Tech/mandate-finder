import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.ab_test import SendTimeRecommendation
from src.services.ab_test_service import ABTestService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


class TestOptimalSendTime:
    def test_returns_default_when_no_data(self, db_session):
        service = ABTestService(db_session)
        result = service.get_optimal_send_time("director-tech")
        assert result["persona_key"] == "director-tech"
        assert result["optimal_hour_utc"] == 14
        assert result["confidence"] == 0.0
        assert result["sample_size"] == 0

    def test_returns_recommendation_when_exists(self, db_session):
        rec = SendTimeRecommendation(persona_key="director-tech", optimal_hour_utc=10,
                                      optimal_day_of_week=3, confidence=0.85, sample_size=120)
        db_session.add(rec)
        db_session.commit()
        service = ABTestService(db_session)
        result = service.get_optimal_send_time("director-tech")
        assert result["optimal_hour_utc"] == 10
        assert result["optimal_day_of_week"] == 3
        assert result["confidence"] == 0.85
        assert result["sample_size"] == 120
