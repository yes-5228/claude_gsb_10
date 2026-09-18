"""保障值守模块接口测试：对象展开、加密排班、状态流转、问题归属与小结。"""

from datetime import date, timedelta

from tests.conftest import full_items

API = "/api/v1"


def _restroom(client, district="保障区", status="正常开放", manager="管理员", name=None):
    payload = {
        "name": name or f"{district}-{status}-公厕",
        "district": district,
        "address": "测试路 1 号",
        "grade": "二类",
        "status": status,
        "manager": manager,
        "stall_count": 4,
        "basin_count": 2,
    }
    resp = client.post(f"{API}/restrooms", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assurance_payload(client, restroom_ids, *, level="二级保障", start=None, end=None, **extra):
    today = date.today()
    payload = {
        "name": "节假日重点保障",
        "assurance_type": "节假日保障",
        "level": level,
        "start_date": (start or today).isoformat(),
        "end_date": (end or today).isoformat(),
        "districts": [],
        "restroom_ids": restroom_ids,
        "requirements": ["重点公厕随脏随保", "耗材备货翻倍"],
        "contact": "值班室",
    }
    payload.update(extra)
    return payload


def _create_assurance(client, restroom_ids, **kw):
    payload = _assurance_payload(client, restroom_ids, **kw)
    resp = client.post(f"{API}/assurances", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _start(client, assurance_id, operator="值班长"):
    return client.post(
        f"{API}/assurances/{assurance_id}/start", json={"operator": operator}
    )


def _finish(client, assurance_id, operator="值班长"):
    return client.post(
        f"{API}/assurances/{assurance_id}/finish", json={"operator": operator}
    )


def _issue(client, restroom_id, **kw):
    payload = {"title": "保障期问题", "restroom_id": restroom_id}
    payload.update(kw)
    resp = client.post(f"{API}/issues", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_dictionaries_include_assurance(client):
    data = client.get(f"{API}/meta/dictionaries").json()
    assert "一级保障" in data["assurance_level"]
    assert data["assurance_status"] == ["筹备中", "保障中", "已结束", "已取消"]
    assert data["assurance_transitions"]["筹备中"] == ["保障中", "已取消"]
    freq = data["assurance_level_frequency"]
    assert freq["一级保障"]["daily"] == 6
    assert freq["一级保障"]["by_shift"] == {"早班": 2, "中班": 2, "晚班": 2}
    assert freq["三级保障"]["by_shift"]["早班"] == 1


def test_create_expands_targets_and_duties(client):
    district = "展开专用区"
    normal1 = _restroom(client, district, manager="甲")
    normal2 = _restroom(client, district, manager="乙")
    _restroom(client, district, status="维修中", manager="丙")  # 维修中不纳入
    other = _restroom(client, "另外一个区", manager="丁")

    detail = _create_assurance(
        client,
        [normal1["id"], normal2["id"], normal1["id"], other["id"]],  # 含重复 id
        districts=[district],
        level="一级保障",
    )
    # 2 座区域内正常开放 + 1 座手动追加；维修中被排除；重复 id 去重
    assert detail["target_count"] == 3
    sources = {t["restroom_id"]: t["source"] for t in detail["targets"]}
    assert sources[normal1["id"]] == "区域纳入"
    assert sources[other["id"]] == "手动指定"
    assert detail["daily_count"] == 6
    assert detail["shift_plan"] == {"早班": 2, "中班": 2, "晚班": 2}

    # 1 天 × 3 班次 × 3 座 = 9 个岗位，值守人非空（责任人回退）且自动轮排
    duties = client.get(
        f"{API}/assurances/{detail['id']}/duties", params={"page_size": 100}
    ).json()
    assert duties["meta"]["total"] == 9
    assert {item["assignee"] for item in duties["items"]} == {"甲", "乙", "丁"}
    by_shift = {}
    for item in duties["items"]:
        by_shift.setdefault(item["shift"], item["planned_count"])
    assert by_shift == {"早班": 2, "中班": 2, "晚班": 2}

    # 频次下限校验
    bad = client.post(
        f"{API}/assurances",
        json=_assurance_payload(client, [normal1["id"]], daily_count=2),
    )
    assert bad.status_code == 422


def test_duty_filter_and_reassign(client):
    room = _restroom(client, "排班过滤区", manager="赵六")
    detail = _create_assurance(
        client, [room["id"]], level="三级保障",
        start=date.today(), end=date.today() + timedelta(days=1),
    )
    morning = client.get(
        f"{API}/assurances/{detail['id']}/duties",
        params={"duty_date": date.today().isoformat(), "shift": "早班"},
    ).json()
    assert morning["meta"]["total"] == 1
    duty_id = morning["items"][0]["id"]

    patched = client.patch(
        f"{API}/assurances/{detail['id']}/duties/{duty_id}",
        json={"assignee": "钱七", "remark": "节日带班"},
    )
    assert patched.status_code == 200
    assert patched.json()["assignee"] == "钱七"
    assert patched.json()["actual_count"] == 0
    assert patched.json()["completed"] is False


def test_status_transitions_and_summary(client):
    room = _restroom(client, "流转区", manager="孙八")
    assurance = _create_assurance(client, [room["id"]])

    # 筹备中不能直接结束
    invalid = _finish(client, assurance["id"])
    assert invalid.status_code == 400
    assert "不允许变更" in invalid.json()["detail"]

    assert _start(client, assurance["id"]).status_code == 200
    # 重复启动报错
    assert _start(client, assurance["id"]).status_code == 400

    # 保障期内上报一个未闭环问题，结束时进入小结
    _issue(client, room["id"], title="客流高峰清洁问题", severity="紧急")

    finished = _finish(client, assurance["id"])
    assert finished.status_code == 200
    body = finished.json()
    assert body["status"] == "已结束"
    assert body["finished_at"] is not None
    summary = body["summary"]
    assert summary is not None
    assert summary["target_count"] == 1
    assert summary["issue_total"] == 1
    assert summary["issue_open"] == 1
    assert {c["name"] for c in summary["issue_by_category"]}
    severity_map = {item["name"]: item["value"] for item in summary["issue_by_severity"]}
    assert severity_map["紧急"] == 1
    # 终态不能再改派
    duty = client.get(f"{API}/assurances/{body['id']}/duties", params={"page_size": 5}).json()["items"][0]
    blocked = client.patch(
        f"{API}/assurances/{body['id']}/duties/{duty['id']}", json={"assignee": "新人"}
    )
    assert blocked.status_code == 400


def test_edit_constraints_and_rebuild_keeps_assignment(client):
    room = _restroom(client, "编辑区", manager="周九")
    assurance = _create_assurance(client, [room["id"]], level="三级保障")

    duty_id = client.get(
        f"{API}/assurances/{assurance['id']}/duties", params={"shift": "早班"}
    ).json()["items"][0]["id"]
    client.patch(
        f"{API}/assurances/{assurance['id']}/duties/{duty_id}",
        json={"assignee": "保留的改派人"},
    )

    # 筹备中延长时段触发重建，原岗位的手工改派保留
    rebuilt = client.patch(
        f"{API}/assurances/{assurance['id']}",
        json={"end_date": (date.today() + timedelta(days=1)).isoformat()},
    ).json()
    duties = client.get(
        f"{API}/assurances/{assurance['id']}/duties",
        params={"duty_date": date.today().isoformat(), "shift": "早班"},
    ).json()["items"]
    assert duties[0]["assignee"] == "保留的改派人"
    assert client.get(
        f"{API}/assurances/{assurance['id']}/duties", params={"page_size": 100}
    ).json()["meta"]["total"] == 6
    assert rebuilt["status"] == "筹备中"

    # 启动后结构性字段被拒绝，非结构性字段允许
    _start(client, assurance["id"])
    denied = client.patch(
        f"{API}/assurances/{assurance['id']}", json={"level": "一级保障"}
    )
    assert denied.status_code == 400
    ok = client.patch(
        f"{API}/assurances/{assurance['id']}", json={"requirements": ["新的保障要求"]}
    )
    assert ok.status_code == 200
    assert ok.json()["requirements"] == ["新的保障要求"]

    # 结束后禁止编辑
    _finish(client, assurance["id"])
    assert client.patch(f"{API}/assurances/{assurance['id']}", json={"name": "改名"}).status_code == 400


def test_issue_auto_and_manual_assurance(client):
    target = _restroom(client, "自动归属区", manager="吴十")
    outsider = _restroom(client, "区外区", manager="路人")
    today = date.today()

    active = _create_assurance(
        client, [target["id"]], level="二级保障",
        start=today - timedelta(days=1), end=today + timedelta(days=1),
    )
    past = _create_assurance(
        client, [target["id"]], level="三级保障",
        start=today - timedelta(days=10), end=today - timedelta(days=6),
    )

    # 时段内 + 重点对象：自动归属
    hit = _issue(client, target["id"])
    assert hit["assurance_id"] == active["id"]
    assert hit["assurance"]["level"] == "二级保障"

    # 非重点对象：不归属
    no_link = _issue(client, outsider["id"])
    assert no_link["assurance_id"] is None

    # 把区外厕挂到不含它的保障应被拒绝（不属于重点对象）
    wrong = client.patch(
        f"{API}/issues/{no_link['id']}", json={"assurance_id": past["id"]}
    )
    assert wrong.status_code == 400

    # 手动挂到包含该厕的保障、再解除
    other_assurance = _create_assurance(client, [outsider["id"]])
    linked = client.patch(
        f"{API}/issues/{no_link['id']}", json={"assurance_id": other_assurance["id"]}
    )
    assert linked.status_code == 200
    assert linked.json()["assurance_id"] == other_assurance["id"]
    detached = client.patch(
        f"{API}/issues/{no_link['id']}", json={"assurance_id": None}
    )
    assert detached.json()["assurance_id"] is None

    # 列表按保障过滤
    listed = client.get(f"{API}/issues", params={"assurance_id": active["id"]}).json()
    assert listed["meta"]["total"] == 1
    assert listed["items"][0]["id"] == hit["id"]


def test_overlapping_assurance_prefers_higher_level(client):
    room = _restroom(client, "重叠区", manager="郑十一")
    today = date.today()
    level2 = _create_assurance(client, [room["id"]], level="二级保障",
                               start=today, end=today + timedelta(days=2))
    level1 = _create_assurance(client, [room["id"]], level="一级保障",
                               start=today, end=today + timedelta(days=2))
    issue = _issue(client, room["id"])
    assert issue["assurance_id"] == level1["id"]
    assert level2["id"] != level1["id"]


def test_inspection_completion_progress(client):
    room = _restroom(client, "完成率区", manager="冯十二")
    assurance = _create_assurance(client, [room["id"]], level="三级保障")  # 每班次 1 次

    # 早/中/晚各巡查 1 次 → 当天 3 个岗位全部完成
    for shift in ("早班", "中班", "晚班"):
        resp = client.post(
            f"{API}/inspections",
            json={
                "restroom_id": room["id"],
                "inspector": "冯十二",
                "shift": shift,
                "items": full_items(9),
            },
        )
        assert resp.status_code == 201, resp.text

    detail = client.get(f"{API}/assurances/{assurance['id']}").json()
    progress = detail["progress"]
    assert progress["due_duty_count"] == 3
    assert progress["completed_duty_count"] == 3
    assert progress["duty_completion_rate"] == 100.0
    assert progress["inspection_completion_rate"] == 100.0

    duties = client.get(f"{API}/assurances/{assurance['id']}/duties", params={"page_size": 10}).json()
    assert all(item["completed"] for item in duties["items"])


def test_relink_and_delete_guard(client):
    room = _restroom(client, "删除保护去重区", manager="陈十三")
    today = date.today()
    assurance = _create_assurance(
        client, [room["id"]], start=today - timedelta(days=1), end=today + timedelta(days=1)
    )
    issue = _issue(client, room["id"])  # 自动归集
    assert issue["assurance_id"] == assurance["id"]

    # 有关联问题时删除被拒绝
    blocked = client.delete(f"{API}/assurances/{assurance['id']}")
    assert blocked.status_code == 409
    # force 删除后问题解除归属
    forced = client.delete(f"{API}/assurances/{assurance['id']}", params={"force": "true"})
    assert forced.status_code == 200
    assert client.get(f"{API}/issues/{issue['id']}").json()["assurance_id"] is None

    # 保障进行中不允许删除
    active_one = _create_assurance(client, [room["id"]])
    _start(client, active_one["id"])
    assert client.delete(f"{API}/assurances/{active_one['id']}").status_code == 409
