import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { assuranceApi } from '../../api/assurance.js';
import { issueApi } from '../../api/issues.js';
import { AssuranceLevelTag, AssuranceStatusTag, StatusTag } from '../../components/Tags.jsx';
import BarList from '../../components/BarList.jsx';
import DataTable from '../../components/DataTable.jsx';
import DetailList from '../../components/DetailList.jsx';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import Pagination from '../../components/Pagination.jsx';
import StatCard from '../../components/StatCard.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useAsync } from '../../hooks/useAsync.js';
import { useListQuery } from '../../hooks/useListQuery.js';
import { formatDate, formatDateTime } from '../../utils/format.js';
import AssuranceFormModal from './AssuranceFormModal.jsx';

function todayInput() {
  return new Date().toISOString().slice(0, 10);
}

const ACTION_META = {
  start: { label: '启动保障', api: assuranceApi.start, tone: 'btn-primary' },
  finish: { label: '结束并出具小结', api: assuranceApi.finish, tone: 'btn-primary' },
  cancel: { label: '取消保障', api: assuranceApi.cancel, tone: 'btn-danger' },
};

function AssuranceActionModal({ action, onClose, onDone }) {
  const { assuranceId } = useParams();
  const meta = ACTION_META[action];
  const toast = useToast();
  const [operator, setOperator] = useState('');
  const [remark, setRemark] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    if (!operator.trim()) return setError('请填写操作人');
    setSaving(true);
    setError(null);
    try {
      await meta.api(assuranceId, { operator: operator.trim(), remark: remark || null });
      toast.success('操作成功');
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={meta.label}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            返回
          </button>
          <button type="submit" form="assurance-action" className={`btn ${meta.tone}`} disabled={saving}>
            {saving ? '处理中...' : '确认'}
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="assurance-action" className="form-grid" onSubmit={submit}>
        <Field label="操作人 *">
          <input value={operator} onChange={(event) => setOperator(event.target.value)} placeholder="值班长 / 负责人" />
        </Field>
        <Field label="操作说明" full>
          <textarea rows="2" value={remark} onChange={(event) => setRemark(event.target.value)} />
        </Field>
      </form>
    </Modal>
  );
}

function DutyAssignModal({ duty, onClose, onSaved }) {
  const { assuranceId } = useParams();
  const toast = useToast();
  const [assignee, setAssignee] = useState(duty.assignee || '');
  const [remark, setRemark] = useState(duty.remark || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await assuranceApi.updateDuty(assuranceId, duty.id, {
        assignee: assignee.trim(),
        remark: remark || null,
      });
      toast.success('值守岗位已更新');
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={`改派值守 - ${formatDate(duty.duty_date)} ${duty.shift}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            返回
          </button>
          <button type="submit" form="duty-assign" className="btn btn-primary" disabled={saving}>
            保存
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="duty-assign" className="form-grid" onSubmit={submit}>
        <Field label="值守公厕" full>
          <input value={duty.restroom ? `${duty.restroom.code} ${duty.restroom.name}` : ''} disabled />
        </Field>
        <Field label="应巡次数">
          <input value={duty.planned_count} disabled />
        </Field>
        <Field label="值守人 *">
          <input value={assignee} onChange={(event) => setAssignee(event.target.value)} placeholder="姓名" />
        </Field>
        <Field label="岗位备注" full>
          <textarea rows="2" value={remark} onChange={(event) => setRemark(event.target.value)} />
        </Field>
      </form>
    </Modal>
  );
}

export default function AssuranceDetailPage() {
  const { assuranceId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [action, setAction] = useState(null);
  const [showEdit, setShowEdit] = useState(false);
  const [assignDuty, setAssignDuty] = useState(null);
  const [liveSummary, setLiveSummary] = useState(null);

  const { data: assurance, loading, error, reload } = useAsync(
    () => assuranceApi.detail(assuranceId),
    [assuranceId],
  );

  const duties = useListQuery(
    (params) => assuranceApi.duties(assuranceId, params),
    { duty_date: todayInput(), shift: '', restroom_id: '', assignee: '' },
    10,
  );

  const guaranteeIssues = useListQuery(
    (params) => issueApi.list({ ...params, assurance_id: assuranceId }),
    { status: '', keyword: '' },
    10,
  );

  const { data: reassignOptions } = useAsync(
    () =>
      assuranceApi
        .list({ page_size: 100, status: '', sort_by: 'start_date' })
        .then((res) => res.items.filter((item) => item.id !== Number(assuranceId))),
    [assuranceId],
  );

  // 详情加载后，把值守日期默认值收敛到保障时段内（已结束取末日、未开始取首日），避免默认查“今天”为空
  useEffect(() => {
    if (!assurance) return;
    const today = todayInput();
    let target = today;
    if (today < assurance.start_date) target = assurance.start_date;
    else if (today > assurance.end_date) target = assurance.end_date;
    if (target !== duties.filters.duty_date) duties.updateFilter('duty_date', target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assurance?.id]);

  const regenerate = async () => {
    if (!window.confirm('重新自动排班将依据最新人员安排重排，已保留手工改派。确认继续？')) return;
    try {
      await assuranceApi.regenerate(assuranceId);
      toast.success('已重新排班');
      reload();
      duties.reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const doRelink = async () => {
    try {
      const res = await assuranceApi.relink(assuranceId);
      toast.success(`已归集 ${res.relinked} 条保障期内未归属问题`);
      reload();
      guaranteeIssues.reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const refreshSummary = async () => {
    try {
      const detail = await assuranceApi.refreshSummary(assuranceId);
      toast.success('保障小结已刷新归档');
      setLiveSummary(null);
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const loadLiveSummary = async () => {
    try {
      setLiveSummary(await assuranceApi.summary(assuranceId));
    } catch (err) {
      toast.error(err.message);
    }
  };

  const remove = async () => {
    if (!window.confirm('确认删除该保障？已归集问题将解除归属。')) return;
    try {
      await assuranceApi.remove(assuranceId, { force: 'true' });
      toast.success('已删除');
      navigate('/assurances');
    } catch (err) {
      toast.error(err.message);
    }
  };

  const detachIssue = async (row) => {
    if (!window.confirm(`将问题「${row.title}」移出本保障？`)) return;
    try {
      await issueApi.update(row.id, { assurance_id: null });
      toast.success('已移出保障');
      guaranteeIssues.reload();
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const reassignIssue = async (row, targetId) => {
    try {
      await issueApi.update(row.id, { assurance_id: targetId ? Number(targetId) : null });
      toast.success(targetId ? '已改派保障' : '已移出保障');
      guaranteeIssues.reload();
      reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  if (loading && !assurance) return <div className="loading-block">保障信息加载中…</div>;

  const progress = assurance?.progress;
  const summary = liveSummary || assurance?.summary;
  const isPreparing = assurance?.status === '筹备中';
  const isActive = assurance?.status === '保障中';

  return (
    <>
      <PageHeader
        title={assurance ? `${assurance.code} ${assurance.name}` : '保障详情'}
        description="保障时段、重点对象、加密值守与问题汇总"
        actions={
          assurance ? (
            <>
              <Link className="btn" to="/assurances">
                返回列表
              </Link>
              {isPreparing ? (
                <button type="button" className="btn" onClick={() => setShowEdit(true)}>
                  编辑
                </button>
              ) : null}
              {isPreparing ? (
                <button type="button" className="btn" onClick={regenerate}>
                  重新排班
                </button>
              ) : null}
              {isPreparing ? (
                <button type="button" className="btn btn-primary" onClick={() => setAction('start')}>
                  启动保障
                </button>
              ) : null}
              {isActive ? (
                <button type="button" className="btn btn-primary" onClick={() => setAction('finish')}>
                  结束并出具小结
                </button>
              ) : null}
              {(isPreparing || isActive) ? (
                <button type="button" className="btn btn-danger" onClick={() => setAction('cancel')}>
                  取消保障
                </button>
              ) : null}
              <button type="button" className="btn btn-danger" onClick={remove}>
                删除
              </button>
            </>
          ) : null
        }
      />

      <div className="content">
        {error ? <div className="alert alert-error">{error.message}</div> : null}

        {assurance ? (
          <>
            <section className="card">
              <div className="card-title">
                <div className="inline">
                  <h3>{assurance.name}</h3>
                  <AssuranceLevelTag level={assurance.level} />
                  <AssuranceStatusTag status={assurance.status} />
                </div>
                <span className="hint">联络人：{assurance.contact || '未设置'}</span>
              </div>
              <DetailList
                items={[
                  { label: '保障类型', value: assurance.assurance_type },
                  {
                    label: '保障时段',
                    value: `${formatDate(assurance.start_date)} ~ ${formatDate(assurance.end_date)}（共 ${progress?.total_days ?? '-'} 天）`,
                  },
                  {
                    label: '加密频次',
                    value: `每座重点公厕每日 ${assurance.daily_count} 次：早班 ${assurance.shift_plan['早班']} / 中班 ${assurance.shift_plan['中班']} / 晚班 ${assurance.shift_plan['晚班']}`,
                  },
                  {
                    label: '重点对象',
                    value: `${assurance.target_count} 座公厕，覆盖 ${assurance.district_count} 个区域`,
                  },
                  { label: '启动时间', value: formatDateTime(assurance.started_at) },
                  { label: '结束时间', value: formatDateTime(assurance.finished_at) },
                  {
                    label: '保障要求',
                    value: assurance.requirements.length ? (
                      <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {assurance.requirements.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      '无'
                    ),
                  },
                  { label: '备注', value: assurance.remark || '无' },
                ]}
              />
              <div style={{ marginTop: 12 }}>
                <div className="muted" style={{ marginBottom: 6 }}>
                  重点公厕：
                  {assurance.targets.map((target) => (
                    <Link
                      key={target.id}
                      className="tag tag-neutral"
                      to={`/restrooms/${target.restroom_id}`}
                      style={{ marginRight: 6 }}
                    >
                      {target.restroom?.name}（{target.source}）
                    </Link>
                  ))}
                </div>
              </div>
            </section>

            <section className="card">
              <div className="card-title">
                <h3>值守完成情况</h3>
                <span className="hint">统计截至 {progress ? formatDate(progress.as_of) : '-'} 应到的岗位</span>
              </div>
              <div className="stat-grid">
                <StatCard
                  label="重点公厕"
                  value={progress?.target_count ?? 0}
                  unit="座"
                  foot={`覆盖 ${assurance.district_count} 个区域`}
                />
                <StatCard
                  label="值守岗位完成率"
                  value={progress?.duty_completion_rate ?? 0}
                  unit="%"
                  foot={`${progress?.completed_duty_count ?? 0} / ${progress?.due_duty_count ?? 0} 个岗位`}
                  tone={progress?.duty_completion_rate >= 90 ? 'success' : 'warning'}
                />
                <StatCard
                  label="加密巡查完成率"
                  value={progress?.inspection_completion_rate ?? 0}
                  unit="%"
                  foot={`${progress?.actual_inspection_count ?? 0} / ${progress?.planned_inspection_count ?? 0} 次`}
                  tone={progress?.inspection_completion_rate >= 90 ? 'success' : 'warning'}
                />
                <StatCard
                  label="保障期未闭环问题"
                  value={assurance.issue_open}
                  unit="条"
                  foot={`累计归集 ${assurance.issue_total} 条`}
                  tone={assurance.issue_open ? 'danger' : 'success'}
                />
              </div>
            </section>

            <section className="card">
              <div className="card-title">
                <h3>值守安排</h3>
                <span className="hint">按天 × 班次 × 重点公厕自动排岗，可逐岗改派</span>
              </div>
              <div className="filter-bar" style={{ marginBottom: 12 }}>
                <Field label="值守日期">
                  <input
                    type="date"
                    value={duties.filters.duty_date}
                    onChange={(event) => duties.updateFilter('duty_date', event.target.value)}
                  />
                </Field>
                <Field label="班次">
                  <select
                    value={duties.filters.shift}
                    onChange={(event) => duties.updateFilter('shift', event.target.value)}
                  >
                    <option value="">全部</option>
                    <option>早班</option>
                    <option>中班</option>
                    <option>晚班</option>
                  </select>
                </Field>
                <Field label="值守人">
                  <input
                    value={duties.filters.assignee}
                    placeholder="姓名"
                    onChange={(event) => duties.updateFilter('assignee', event.target.value)}
                  />
                </Field>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => {
                    duties.updateFilter('duty_date', '');
                    duties.updateFilter('shift', '');
                    duties.updateFilter('assignee', '');
                  }}
                >
                  查看全部岗位
                </button>
              </div>
              <DataTable
                loading={duties.loading}
                error={duties.error}
                rows={duties.items}
                emptyText="当前筛选下无值守岗位"
                columns={[
                  { key: 'duty_date', title: '日期', render: (row) => formatDate(row.duty_date) },
                  { key: 'shift', title: '班次' },
                  {
                    key: 'restroom',
                    title: '公厕',
                    render: (row) =>
                      row.restroom ? (
                        <Link to={`/restrooms/${row.restroom.id}`}>{row.restroom.name}</Link>
                      ) : (
                        '-'
                      ),
                  },
                  { key: 'planned_count', title: '应巡', render: (row) => `${row.actual_count}/${row.planned_count}` },
                  {
                    key: 'completed',
                    title: '完成',
                    render: (row) => (
                      <span className={`tag ${row.completed ? 'tag-success' : 'tag-warning'}`}>
                        {row.completed ? '已达标' : '未达标'}
                      </span>
                    ),
                  },
                  { key: 'assignee', title: '值守人', render: (row) => row.assignee || <span className="muted">待派</span> },
                  { key: 'remark', title: '备注', wrap: true },
                  {
                    key: 'actions',
                    title: '操作',
                    render: (row) =>
                      isPreparing || isActive ? (
                        <button type="button" className="btn-link" onClick={() => setAssignDuty(row)}>
                          改派
                        </button>
                      ) : (
                        <span className="muted">-</span>
                      ),
                  },
                ]}
              />
              <Pagination meta={duties.meta} onPageChange={duties.setPage} />
            </section>

            <section className="card">
              <div className="card-title">
                <h3>保障期间问题汇总</h3>
                <div className="action-group">
                  <button type="button" className="btn btn-sm" onClick={doRelink}>
                    归集时段内未归属问题
                  </button>
                </div>
              </div>
              <DataTable
                loading={guaranteeIssues.loading}
                error={guaranteeIssues.error}
                rows={guaranteeIssues.items}
                emptyText="保障期间暂无归集问题"
                columns={[
                  { key: 'code', title: '编号' },
                  {
                    key: 'title',
                    title: '问题',
                    wrap: true,
                    render: (row) => <Link to={`/issues/${row.id}`}>{row.title}</Link>,
                  },
                  { key: 'category', title: '分类' },
                  {
                    key: 'status',
                    title: '状态',
                    render: (row) => <StatusTag status={row.status} />,
                  },
                  { key: 'assignee', title: '责任人' },
                  {
                    key: 'change',
                    title: '改派保障',
                    render: (row) => (
                      <select
                        value={row.assurance_id ?? ''}
                        onChange={(event) => reassignIssue(row, event.target.value)}
                      >
                        <option value={assuranceId} disabled>
                          {assurance.name}（当前）
                        </option>
                        <option value="">移出保障</option>
                        {(reassignOptions || []).map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}（{item.level}）
                          </option>
                        ))}
                      </select>
                    ),
                  },
                  {
                    key: 'actions',
                    title: '操作',
                    render: (row) => (
                      <button type="button" className="btn-link danger" onClick={() => detachIssue(row)}>
                        移出
                      </button>
                    ),
                  },
                ]}
              />
              <Pagination meta={guaranteeIssues.meta} onPageChange={guaranteeIssues.setPage} />
            </section>

            <section className="card">
              <div className="card-title">
                <h3>保障情况小结</h3>
                <div className="action-group">
                  <button type="button" className="btn btn-sm" onClick={loadLiveSummary}>
                    查看实时小结
                  </button>
                  <button type="button" className="btn btn-sm btn-primary" onClick={refreshSummary}>
                    {assurance.summary ? '刷新归档小结' : '生成并归档小结'}
                  </button>
                </div>
              </div>
              {assurance.summary_generated_at && !liveSummary ? (
                <span className="hint">归档时间：{formatDateTime(assurance.summary_generated_at)}</span>
              ) : null}
              {summary ? <SummaryView summary={summary} /> : (
                <div className="empty-block">
                  结束保障时将自动出具小结；保障进行中可查看实时小结或手动归档。
                </div>
              )}
            </section>
          </>
        ) : null}
      </div>

      {action ? (
        <AssuranceActionModal
          action={action}
          onClose={() => setAction(null)}
          onDone={() => {
            setAction(null);
            reload();
          }}
        />
      ) : null}

      {showEdit && assurance ? (
        <AssuranceFormModal
          assurance={assurance}
          onClose={() => setShowEdit(false)}
          onSaved={() => {
            setShowEdit(false);
            reload();
            duties.reload();
          }}
        />
      ) : null}

      {assignDuty ? (
        <DutyAssignModal
          duty={assignDuty}
          onClose={() => setAssignDuty(null)}
          onSaved={() => {
            setAssignDuty(null);
            duties.reload();
          }}
        />
      ) : null}
    </>
  );
}

function SummaryView({ summary }) {
  const dist = (items) => items.filter((item) => item.value > 0);
  return (
    <div className="bar-list" style={{ marginTop: 12 }}>
      <DetailList
        items={[
          { label: '保障时段', value: `${formatDate(summary.start_date)} ~ ${formatDate(summary.end_date)}（${summary.days} 天）` },
          { label: '重点对象', value: `${summary.target_count} 座公厕，覆盖 ${summary.district_count} 个区域：${summary.districts.join('、') || '无'}` },
          {
            label: '值守岗位',
            value: `计划 ${summary.duty_planned} 个，应到 ${summary.duty_due} 个，达标 ${summary.duty_completed} 个，完成率 ${summary.duty_completion_rate}%`,
          },
          {
            label: '加密巡查',
            value: `计划 ${summary.inspection_planned} 次，实际 ${summary.inspection_actual} 次，完成率 ${summary.inspection_completion_rate}%，平均得分 ${summary.avg_score ?? '-'}`,
          },
          {
            label: '问题汇总',
            value: `共 ${summary.issue_total} 条，未闭环 ${summary.issue_open} 条，已闭环 ${summary.issue_closed} 条，超期 ${summary.issue_overdue} 条`,
          },
        ]}
      />
      <div className="grid-3">
        <Distribution title="问题分类分布" items={dist(summary.issue_by_category)} />
        <Distribution title="严重程度分布" items={dist(summary.issue_by_severity)} />
        <Distribution title="区域分布" items={dist(summary.issue_by_district)} />
      </div>      {summary.open_items.length ? (
        <div>
          <div className="section-title">未闭环问题（{summary.open_items.length}）</div>
          <DataTable
            rows={summary.open_items}
            columns={[
              { key: 'code', title: '编号' },
              { key: 'title', title: '问题', wrap: true },
              { key: 'restroom_name', title: '公厕' },
              { key: 'category', title: '分类' },
              {
                key: 'severity',
                title: '程度',
                render: (row) => <span className="tag tag-warning">{row.severity}</span>,
              },
              {
                key: 'deadline',
                title: '整改期限',
                render: (row) => formatDateTime(row.deadline),
              },
            ]}
          />
        </div>
      ) : null}
    </div>
  );
}

function Distribution({ title, items }) {
  return (
    <div>
      <div className="section-title">{title}</div>
      {items.length ? (
        <BarList items={items} emptyText="无" />
      ) : (
        <span className="muted">无</span>
      )}
    </div>
  );
}
