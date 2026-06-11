import uuid
from unittest.mock import patch

import pytest

from mandate_finder.models.profile_match import ProfileMatch
from mandate_finder.models.search_profile import SearchProfile
from mandate_finder.services.profile_notifier import ProfileNotifier


@pytest.mark.asyncio
async def test_notify_skips_low_score() -> None:
    notifier = ProfileNotifier()
    profile = SearchProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Test Profile",
        keywords="React",
        notify_on_score_above=0.8,
        notify_channels="email",
    )
    match = ProfileMatch(
        id=uuid.uuid4(),
        profile_id=profile.id,
        job_posting_id=uuid.uuid4(),
        score=0.3,
    )

    with patch.object(notifier, "_send_email") as mock_email:
        await notifier.notify_new_matches(profile, [match])
        mock_email.assert_not_called()


@pytest.mark.asyncio
async def test_notify_high_score_triggers_slack() -> None:
    notifier = ProfileNotifier()
    profile = SearchProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Test Profile",
        keywords="React",
        notify_on_score_above=0.8,
        notify_channels="slack",
    )
    match = ProfileMatch(
        id=uuid.uuid4(),
        profile_id=profile.id,
        job_posting_id=uuid.uuid4(),
        score=0.95,
        reasoning="Good match",
    )

    with (
        patch.object(notifier, "_send_slack") as mock_slack,
        patch.object(notifier, "_send_email") as mock_email,
    ):
        await notifier.notify_new_matches(profile, [match])
        mock_slack.assert_awaited_once()
        mock_email.assert_not_called()
