import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { supportApi } from '../../api/support.js';
import BarList from '../../components/BarList.jsx';
import DataTable from '../../components/DataTable.jsx';
import DetailList from '../../components/DetailList.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import Pagination from '../../components/Pagination.jsx';
import StatCard from '../../components/StatCard.jsx';
import { SeverityTag, StatusTag, SupportLevelTag } from '../../components/Tags.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useAsync } from '../../hooks/useAsync.js';
import { useListQuery } from '../../hooks/useListQuery.js';
import { formatDate, formatDateTime } from '../../utils/format.js';
import SupportFormModal from './SupportFormModal.jsx';

const TABS = [
  { key: 'duties', label: '值守安排' },
  { key: 'issues', label: '保障问题' },
  { key: 'summary', label: '保障小结' },
];

export default function SupportDetailPage() {
  const { planId } = useParams();
  const toast = useToast();
  const [tab, setTab] = useState('duties');
  const [showForm, setShowForm] = useState(false);
  const [conclusion, setConclusion] = useState('');
  const [savingConclusion, setSavingConclusion] = useState(false);

  const {
    data: plan,
    loading,
    error,
    reload: reloadPlan,
  } = useAsync(() => supportApi.detail(planId), [planId]);
  const { data: summary, reload: reloadSummary } = useAsync(
    () => supportApi.summary(planId),
    [planId],
  );
  const issues = useListQuery((params) => supportApi.issues(planId, params), {}, 5);

  useEffect(() => {
    setConclusion(plan?.conclusion ?? '');
  }, [plan?.conclusion]);

  const reloadAll = () => {
    reloadPlan();
    reloadSummary();
    issues.reload();
  };

  const run = async (action, confirmText, successText) => {
    if (confirmText && !window.confirm(confirmText)) return;
    try {
      await action();
      toast.success(successText);
      reloadAll();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const saveConclusion = async () => {
    setSavingConclusion(true);
    try {
      await supportApi.update(planId, { conclusion });
      toast.success('保障小结已保存');
      reloadPlan();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSavingConclusion(false);
    }
  };

  const dutyRows = plan?.duties ?? [];

  return (
    <>
      <PageHeader
        title={plan ? `${plan.name}（${plan.code}）` : '保障方案详情'}
        description={
          plan
            ? `${plan.category} · ${formatDate(plan.start_date)} ~ ${formatDate(plan.end_date)}`
            : '加载中…'
        }
        actions={
          <>
            <Link className="btn" to="/support">
              返回列表
            </Link>
            {plan?.status === '筹备中' ? (
              <>
                <button
                  type="button"
                  className="btn"
                  onClick={() =>
                    run(
                      () => supportApi.generateDuties(planId),
                      dutyRows.length ? '将按等级班次重新生成值守安排，现有安排会被覆盖，继续？' : null,
                      '值守安排已生成',
                    )
                  }
                >
                  生成值守安排
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() =>
                    run(
                      () => supportApi.activate(planId),
                      '启动保障后将按等级自动加密巡查频次并生成值守安排，确认启动？',
                      '保障已启动',
                    )
                  }
                >
                  启动保障
                </button>
              </>
            ) : null}
            {plan?.status === '进行中' ? (
              <>
                <button
                  type="button"
                  className="btn"
                  onClick={() =>
                    run(
                      () => supportApi.generateDuties(planId),
                      '将按等级班次重新生成值守安排，现有安排会被覆盖，继续？',
                      '值守安排已重新生成',
                    )
                  }
                >
                  重新生成值守
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() =>
                    run(
                      () => supportApi.finish(planId),
                      '结束保障后将自动生成保障情况小结，确认结束？',
                      '保障已结束，小结已生成',
                    )
                  }
                >
                  结束保障
                </button>
              </>
            ) : null}
            <button type="button" className="btn" onClick={() => setShowForm(true)}>
              编辑方案
            </button>
          </>
        }
      />
      <div className="content">
        {error ? <div className="alert alert-error">{error.message}</div> : null}
        {loading && !plan ? <div className="loading-block">加载中…</div> : null}

        {plan ? (
          <>
            <div className="stat-grid">
              <StatCard
                label="保障状态"
                value={<StatusTag status={plan.status} />}
                foot={`保障等级：${plan.level}`}
              />
              <StatCard
                label="重点公厕"
                value={plan.key_restroom_count}
                unit="座"
                tone="info"
                foot={plan.districts?.length ? plan.districts.join('、') : '指定公厕'}
              />
              <StatCard
                label="巡查覆盖"
                value={summary ? `${summary.actual_inspections}/${summary.expected_inspections}` : '-'}
                unit="次"
                foot={summary ? `覆盖率 ${summary.coverage_rate}% · 应 ${plan.inspections_per_day} 次/日/座` : ''}
              />
              <StatCard
                label="保障期间问题"
                value={summary ? summary.issue_total : '-'}
                unit="件"
                tone={summary?.issue_open ? 'danger' : 'primary'}
                foot={summary ? `未闭环 ${summary.issue_open} 件 · 整改率 ${summary.issue_done_rate}%` : ''}
              />
            </div>

            <div className="inline">
              {TABS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`btn btn-sm${tab === item.key ? ' btn-primary' : ''}`}
                  onClick={() => setTab(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {tab === 'duties' ? (
              <>
                <section className="card">
                  <div className="card-title">
                    <h3>保障信息</h3>
                    <span className="hint">
                      <SupportLevelTag level={plan.level} /> 每公厕每日巡查 {plan.inspections_per_day} 次
                    </span>
                  </div>
                  <DetailList
                    items={[
                      { label: '保障编号', value: plan.code },
                      { label: '保障类型', value: plan.category },
                      { label: '保障等级', value: <SupportLevelTag level={plan.level} /> },
                      {
                        label: '保障时段',
                        value: `${formatDate(plan.start_date)} ~ ${formatDate(plan.end_date)}`,
                      },
                      {
                        label: '重点区域',
                        value: plan.districts?.length ? plan.districts.join('、') : '指定重点公厕',
                      },
                      {
                        label: '重点公厕',
                        value: plan.key_restrooms?.length
                          ? plan.key_restrooms.map((room) => room.name).join('、')
                          : '未覆盖',
                      },
                      { label: '巡查频次', value: `每公厕每日 ${plan.inspections_per_day} 次` },
                      {
                        label: '值守人员',
                        value: plan.staff_pool?.length ? plan.staff_pool.join('、') : '未维护',
                      },
                      { label: '保障要求', value: plan.requirements || '无' },
                      { label: '创建时间', value: formatDateTime(plan.created_at) },
                    ]}
                  />
                </section>

                <section className="card">
                  <div className="card-title">
                    <h3>值守安排（{dutyRows.length} 个班次）</h3>
                    <span className="hint">按保障等级自动生成，人员轮值</span>
                  </div>
                  <DataTable
                    rows={dutyRows}
                    emptyText="尚未生成值守安排，启动保障或点击「生成值守安排」"
                    columns={[
                      { key: 'duty_date', title: '值守日期', render: (row) => formatDate(row.duty_date) },
                      { key: 'shift', title: '班次' },
                      { key: 'staff', title: '值守人员' },
                      { key: 'phone', title: '联系电话', render: (row) => row.phone || '-' },
                      { key: 'note', title: '备注', render: (row) => row.note || '-' },
                    ]}
                  />
                </section>
              </>
            ) : null}

            {tab === 'issues' ? (
              <section className="card">
                <div className="card-title">
                  <h3>保障期间问题（单独汇总）</h3>
                  <Link className="hint" to="/issues">
                    前往整改模块 →
                  </Link>
                </div>
                <DataTable
                  loading={issues.loading}
                  error={issues.error}
                  rows={issues.items}
                  emptyText="保障期间暂无问题上报"
                  columns={[
                    { key: 'code', title: '编号' },
                    {
                      key: 'title',
                      title: '问题',
                      wrap: true,
                      render: (row) => <Link to={`/issues/${row.id}`}>{row.title}</Link>,
                    },
                    {
                      key: 'restroom',
                      title: '公厕',
                      render: (row) => row.restroom?.name ?? '-',
                    },
                    { key: 'category', title: '分类' },
                    { key: 'severity', title: '程度', render: (row) => <SeverityTag severity={row.severity} /> },
                    { key: 'status', title: '状态', render: (row) => <StatusTag status={row.status} /> },
                    { key: 'report_time', title: '上报时间', render: (row) => formatDateTime(row.report_time) },
                  ]}
                />
                <Pagination meta={issues.meta} onPageChange={issues.setPage} />
              </section>
            ) : null}

            {tab === 'summary' ? (
              <>
                <section className="card">
                  <div className="card-title">
                    <h3>保障情况小结</h3>
                    <span className="hint">统计口径：保障时段内、重点公厕范围</span>
                  </div>
                  {summary ? (
                    <div className="stat-grid">
                      <StatCard
                        label="值守班次"
                        value={summary.duty_total}
                        unit="个"
                        tone="info"
                        foot={`累计 ${summary.duty_staff_total} 人次`}
                      />
                      <StatCard
                        label="巡查覆盖率"
                        value={summary.coverage_rate}
                        unit="%"
                        foot={`应巡 ${summary.expected_inspections} 次 · 实巡 ${summary.actual_inspections} 次`}
                      />
                      <StatCard
                        label="巡查均分"
                        value={summary.avg_score}
                        unit="分"
                        foot="保障期间巡查记录"
                      />
                      <StatCard
                        label="问题整改率"
                        value={summary.issue_done_rate}
                        unit="%"
                        tone={summary.issue_open ? 'warning' : 'primary'}
                        foot={`共 ${summary.issue_total} 件 · 未闭环 ${summary.issue_open} 件`}
                      />
                    </div>
                  ) : (
                    <div className="loading-block">统计加载中…</div>
                  )}
                </section>

                {summary ? (
                  <div className="grid-2">
                    <section className="card">
                      <div className="card-title">
                        <h3>问题分类分布</h3>
                      </div>
                      <BarList
                        items={summary.issue_by_category.filter((item) => item.value > 0)}
                        emptyText="保障期间无问题"
                      />
                    </section>
                    <section className="card">
                      <div className="card-title">
                        <h3>问题严重程度分布</h3>
                      </div>
                      <BarList
                        items={summary.issue_by_severity.filter((item) => item.value > 0)}
                        emptyText="保障期间无问题"
                      />
                    </section>
                  </div>
                ) : null}

                {summary?.open_issues?.length ? (
                  <section className="card">
                    <div className="card-title">
                      <h3>未闭环问题（{summary.issue_open}）</h3>
                      <span className="hint">保障结束后仍需跟踪整改</span>
                    </div>
                    <DataTable
                      rows={summary.open_issues}
                      columns={[
                        { key: 'code', title: '编号' },
                        {
                          key: 'title',
                          title: '问题',
                          wrap: true,
                          render: (row) => <Link to={`/issues/${row.id}`}>{row.title}</Link>,
                        },
                        { key: 'severity', title: '程度', render: (row) => <SeverityTag severity={row.severity} /> },
                        { key: 'status', title: '状态', render: (row) => <StatusTag status={row.status} /> },
                        { key: 'deadline', title: '整改期限', render: (row) => formatDateTime(row.deadline) },
                      ]}
                    />
                  </section>
                ) : null}

                <section className="card">
                  <div className="card-title">
                    <h3>小结报告</h3>
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => setConclusion(summary?.summary_text ?? '')}
                    >
                      重新生成草稿
                    </button>
                  </div>
                  <textarea
                    rows="5"
                    value={conclusion}
                    placeholder="结束保障后自动生成小结草稿，可在此修改"
                    onChange={(event) => setConclusion(event.target.value)}
                  />
                  <div className="inline" style={{ marginTop: 10 }}>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={savingConclusion}
                      onClick={saveConclusion}
                    >
                      {savingConclusion ? '保存中…' : '保存小结'}
                    </button>
                  </div>
                </section>
              </>
            ) : null}
          </>
        ) : null}
      </div>

      {showForm && plan ? (
        <SupportFormModal plan={plan} onClose={() => setShowForm(false)} onSaved={reloadAll} />
      ) : null}
    </>
  );
}
