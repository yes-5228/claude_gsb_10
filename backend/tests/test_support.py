"""节假日与重大活动保障模块的接口级测试。"""

import itertools
from datetime import date, datetime, timedelta

import pytest

from tests.conftest import full_items

_DISTRICT_SEQ = itertools.count(1)


@pytest.fixture
def support_restroom(client) -> dict:
    """在独立区域内创建公厕，避免与其他用例的台账数据互相干扰。"""
    response = client.post(
        "/api/v1/restrooms",
        json={
            "name": "保障测试公厕",
            "district": f"保障专区-{next(_DISTRICT_SEQ)}",
            "address": "保障路 1 号",
            "grade": "二类",
            "status": "正常开放",
            "manager": "保障责任人",
            "stall_count": 6,
            "basin_count": 3,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _plan_payload(restroom, **overrides):
    today = date.today()
    payload = {
        "name": "测试假期保障",
        "category": "节假日",
        "level": "二级",
        "start_date": (today - timedelta(days=1)).isoformat(),
        "end_date": (today + timedelta(days=2)).isoformat(),
        "districts": [restroom["district"]],
        "requirements": "加密巡查，问题即报即改",
        "staff_pool": ["张三", "李四"],
    }
    payload.update(overrides)
    return payload


def test_support_plan_crud_and_validation(client, support_restroom):
    created = client.post("/api/v1/support-plans", json=_plan_payload(support_restroom)).json()
    assert created["code"].startswith("BZ-")
    assert created["status"] == "筹备中"
    # 二级保障默认每日 2 次巡查
    assert created["inspections_per_day"] == 2
    assert created["key_restroom_count"] == 1

    listed = client.get("/api/v1/support-plans", params={"level": "二级"}).json()
    assert listed["meta"]["total"] >= 1

    detail = client.get(f"/api/v1/support-plans/{created['id']}").json()
    assert detail["key_restrooms"][0]["id"] == support_restroom["id"]

    updated = client.patch(
        f"/api/v1/support-plans/{created['id']}", json={"level": "一级"}
    ).json()
    # 等级调整后自动带出新的默认频次
    assert updated["level"] == "一级"
    assert updated["inspections_per_day"] == 3

    removed = client.delete(f"/api/v1/support-plans/{created['id']}")
    assert removed.status_code == 200
    assert client.get(f"/api/v1/support-plans/{created['id']}").status_code == 404


def test_support_plan_date_validation(client, support_restroom):
    today = date.today()
    bad = _plan_payload(
        support_restroom,
        start_date=today.isoformat(),
        end_date=(today - timedelta(days=1)).isoformat(),
    )
    assert client.post("/api/v1/support-plans", json=bad).status_code == 422

    ok = client.post("/api/v1/support-plans", json=_plan_payload(support_restroom)).json()
    too_late = client.patch(
        f"/api/v1/support-plans/{ok['id']}",
        json={"end_date": (today - timedelta(days=5)).isoformat()},
    )
    assert too_late.status_code == 400


def test_support_activate_generates_duties(client, support_restroom):
    plan = client.post(
        "/api/v1/support-plans",
        json=_plan_payload(support_restroom, level="一级", staff_pool=["张三", "李四", "王五"]),
    ).json()

    activated = client.post(f"/api/v1/support-plans/{plan['id']}/activate").json()
    assert activated["status"] == "进行中"
    # 一级保障：4 天 × 3 班 = 12 个值守班次，人员轮值
    assert len(activated["duties"]) == 12
    staffs = {duty["staff"] for duty in activated["duties"]}
    assert staffs == {"张三", "李四", "王五"}
    shifts = {duty["shift"] for duty in activated["duties"]}
    assert shifts == {"早班", "中班", "晚班"}

    # 重复启动、越级流转均被拒绝
    assert client.post(f"/api/v1/support-plans/{plan['id']}/activate").status_code == 400

    # 重新生成值守：先清空再按规则重建
    regenerated = client.post(f"/api/v1/support-plans/{plan['id']}/duties/generate").json()
    assert len(regenerated) == 12

    finished = client.post(f"/api/v1/support-plans/{plan['id']}/finish").json()
    assert finished["status"] == "已结束"
    assert finished["conclusion"]  # 自动生成小结草稿

    assert client.post(f"/api/v1/support-plans/{plan['id']}/finish").status_code == 400


def test_support_issues_aggregation(client, support_restroom):
    today = date.today()
    plan = client.post(
        "/api/v1/support-plans",
        json=_plan_payload(
            support_restroom,
            start_date=(today - timedelta(days=1)).isoformat(),
            end_date=(today + timedelta(days=1)).isoformat(),
        ),
    ).json()

    # 保障期内、范围内公厕的问题
    in_scope = client.post(
        "/api/v1/issues",
        json={
            "restroom_id": support_restroom["id"],
            "title": "保障期内问题",
            "category": "保洁不到位",
            "severity": "严重",
            "report_time": datetime.now().isoformat(),
        },
    ).json()
    # 保障期外的问题（3 天前）
    client.post(
        "/api/v1/issues",
        json={
            "restroom_id": support_restroom["id"],
            "title": "保障期外问题",
            "category": "其他",
            "report_time": (datetime.now() - timedelta(days=3)).isoformat(),
        },
    )
    # 范围外公厕的问题
    other = client.post(
        "/api/v1/restrooms",
        json={"name": "范围外公厕", "district": "其他区", "address": "别处", "manager": "路人"},
    ).json()
    client.post(
        "/api/v1/issues",
        json={"restroom_id": other["id"], "title": "范围外问题", "category": "其他"},
    )

    aggregated = client.get(f"/api/v1/support-plans/{plan['id']}/issues").json()
    assert aggregated["meta"]["total"] == 1
    assert aggregated["items"][0]["id"] == in_scope["id"]


def test_support_summary(client, support_restroom):
    today = date.today()
    plan = client.post(
        "/api/v1/support-plans",
        json=_plan_payload(
            support_restroom,
            level="二级",
            start_date=today.isoformat(),
            end_date=today.isoformat(),
        ),
    ).json()

    client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": support_restroom["id"],
            "inspector": "保障巡查员",
            "items": full_items(9),
        },
    )
    client.post(
        "/api/v1/issues",
        json={
            "restroom_id": support_restroom["id"],
            "title": "保障期间耗材缺失",
            "category": "耗材缺失",
            "severity": "一般",
        },
    )

    summary = client.get(f"/api/v1/support-plans/{plan['id']}/summary").json()
    # 1 天 × 1 座公厕 × 每日 2 次 = 应巡 2 次
    assert summary["expected_inspections"] == 2
    assert summary["actual_inspections"] == 1
    assert summary["coverage_rate"] == 50.0
    assert summary["issue_total"] == 1
    assert summary["issue_open"] == 1
    assert summary["avg_score"] == 90.0
    assert "保障" in summary["summary_text"]
    category_map = {item["name"]: item["value"] for item in summary["issue_by_category"]}
    assert category_map["耗材缺失"] == 1

    # 结束保障后小结写入方案
    client.post(f"/api/v1/support-plans/{plan['id']}/activate")
    finished = client.post(f"/api/v1/support-plans/{plan['id']}/finish").json()
    assert "巡查覆盖率" in finished["conclusion"]


def test_dictionaries_include_support(client):
    payload = client.get("/api/v1/meta/dictionaries").json()
    assert payload["support_category"] == ["节假日", "重大活动"]
    assert payload["support_level"] == ["一级", "二级", "三级"]
    assert payload["support_status"] == ["筹备中", "进行中", "已结束"]
    assert payload["support_level_rules"]["一级"]["inspections_per_day"] == 3
    assert payload["support_level_rules"]["一级"]["shifts"] == ["早班", "中班", "晚班"]
