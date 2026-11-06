"""Quote-only feeds must initialise report counts for each individual post."""
import sqlite3
from importlib.resources import files

import pytest

from oasis.social_platform.platform_utils import PlatformUtils
from oasis.social_platform.typing import RecsysType


@pytest.fixture
def feed():
    with sqlite3.connect(":memory:") as db:
        schema = files("oasis").joinpath("social_platform/schema")
        db.executescript(schema.joinpath("post.sql").read_text())
        db.executescript(schema.joinpath("comment.sql").read_text())
        db.executemany(
            "INSERT INTO post (post_id, user_id, original_post_id, content, "
            "quote_content, created_at, num_likes, num_dislikes, num_shares, num_reports) "
            "VALUES (?, ?, ?, ?, ?, '2026-01-01', 0, 0, 0, ?)",
            [(1, 10, None, "Original", None, 7),
             (2, 20, 1, "Original", "Quote with no reports", 0),
             (3, 30, 1, "Original", "Reported quote", 2),
             (4, 40, 1, "Original", None, 0)])
        utils = PlatformUtils(db, db.cursor(), None, None, False,
                              RecsysType.TWITTER, report_threshold=1)

        def render(ids):
            rows = [db.execute(
                "SELECT post_id, user_id, original_post_id, content, "
                "quote_content, created_at, num_likes, num_dislikes, num_shares "
                "FROM post WHERE post_id = ?", (post_id,)).fetchone()
                for post_id in ids]
            return utils._add_comments_to_posts(rows)

        yield render


def test_quote_can_be_first_or_only_feed_item(feed):
    post, = feed([2])
    assert post["post_id"] == 2
    assert post["num_reports"] == 0
    assert not post["content"].startswith("[Warning:")


@pytest.mark.parametrize("ids", [[1, 2, 3], [3, 2, 1]])
def test_quote_reports_do_not_leak_from_another_post(feed, ids):
    posts = {post["post_id"]: post for post in feed(ids)}
    assert posts[1]["num_reports"] == 7
    assert posts[2]["num_reports"] == 0
    assert posts[3]["num_reports"] == 2
    assert not posts[2]["content"].startswith("[Warning:")
    assert posts[3]["content"].startswith("[Warning: This post has been reported 2 times]")


def test_repost_still_reads_root_post_reports(feed):
    post, = feed([4])
    assert post["post_id"] == 4
    assert post["num_reports"] == 7
    assert post["content"].startswith("[Warning: This post has been reported 7 times]")
