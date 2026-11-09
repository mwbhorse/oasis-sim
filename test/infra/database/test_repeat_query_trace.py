# =========== Copyright 2023 @ CAMEL-AI.org. All Rights Reserved. ===========
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =========== Copyright 2023 @ CAMEL-AI.org. All Rights Reserved. ===========
"""验证固定模拟时刻的重复查询逐次留痕，真实写库错误仍如实返回。"""

import sqlite3

import pytest

QUERIES = [
    ("refresh", ()),
    ("search_posts", ("coffee",)),
    ("search_user", ("reader",)),
    ("trend", ()),
]


@pytest.fixture
def platform(tmp_path, monkeypatch):
    """使用真实建表代码和固定时钟，推荐列表仅包含一个确定的帖子。"""
    monkeypatch.chdir(tmp_path)
    from oasis.clock.clock import Clock
    from oasis.social_platform.platform import Platform

    instance = Platform(str(tmp_path / "simulation.db"),
                        sandbox_clock=Clock(), recsys_type="twitter")
    instance.db.execute("INSERT INTO user (user_id, user_name) "
                        "VALUES (0, 'reader')")
    instance.db.execute("INSERT INTO post (post_id, user_id, content, "
                        "created_at) VALUES (1, 0, 'coffee', 0)")
    instance.db.execute("INSERT INTO rec (user_id, post_id) VALUES (0, 1)")
    instance.db.commit()
    yield instance
    instance.db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action,args", QUERIES)
async def test_identical_queries_record_distinct_rows(platform, action, args):
    """同一用户、时刻、动作和内容可以重复，rowid 区分每一次调用。"""
    first = await getattr(platform, action)(0, *args)
    second = await getattr(platform, action)(0, *args)
    assert first["success"] is True
    assert first == second
    rows = platform.db.execute(
        "SELECT rowid, user_id, created_at, action, info FROM trace "
        "WHERE action = ? ORDER BY rowid", (action, )).fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]
    assert rows[0][1:] == rows[1][1:]
    assert platform.sandbox_clock.time_step == 0
    assert platform.db.execute("PRAGMA integrity_check").fetchone() == ("ok", )


def test_trace_keeps_columns_and_foreign_key_without_unique_index(platform):
    """只移除联合主键，四个原字段和用户外键保持原样。"""
    columns = platform.db.execute("PRAGMA table_info(trace)").fetchall()
    assert [(row[1], row[2]) for row in columns] == [
        ("user_id", "INTEGER"), ("created_at", "DATETIME"),
        ("action", "TEXT"), ("info", "TEXT")]
    assert all(row[5] == 0 for row in columns)
    assert platform.db.execute("PRAGMA index_list(trace)").fetchall() == []
    foreign_keys = platform.db.execute("PRAGMA foreign_key_list(trace)")
    assert [(row[2], row[3], row[4]) for row in foreign_keys] == [
        ("user", "user_id", "user_id")]
    platform.db.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        platform.pl_utils._record_trace(999, "refresh", {"posts": []})


@pytest.mark.asyncio
@pytest.mark.parametrize("action,args", QUERIES)
async def test_query_trace_write_failure_is_not_swallowed(platform, action,
                                                        args):
    """只读数据库可以查询，但日志写入失败时动作必须报告原始错误。"""
    platform.db.execute("PRAGMA query_only = ON")
    result = await getattr(platform, action)(0, *args)
    assert result["success"] is False
    assert "readonly" in result["error"]
    assert platform.db.execute("SELECT COUNT(*) FROM trace").fetchone() == (0, )
