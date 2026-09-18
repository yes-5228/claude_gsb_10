import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { supportApi } from '../../api/support.js';
import DataTable from '../../components/DataTable.jsx';
import Field from '../../components/Field.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import Pagination from '../../components/Pagination.jsx';
import { StatusTag, SupportLevelTag } from '../../components/Tags.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import { useListQuery } from '../../hooks/useListQuery.js';
import { formatDate } from '../../utils/format.js';
import SupportFormModal from './SupportFormModal.jsx';

const DEFAULT_FILTERS = {
  keyword: '',
  category: '',
  level: '',
  status: '',
};

export default function SupportListPage() {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);

  const list = useListQuery((params) => supportApi.list(params), DEFAULT_FILTERS, 10);

  const run = async (action, confirmText, successText) => {
    if (confirmText && !window.confirm(confirmText)) return;
    try {
      await action();
      toast.success(successText);
      list.reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <>
      <PageHeader
        title="节假日与重大活动保障"
        description="维护保障时段、重点区域与保障要求，按保障等级自动加密巡查频次并生成值守安排"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
            + 新增保障方案
          </button>
        }
      />
      <div className="content">
        <section className="card">
          <div className="filter-bar">
            <Field label="关键字" full>
              <input
                value={list.filters.keyword}
                placeholder="保障名称 / 编号 / 要求"
                onChange={(event) => list.updateFilter('keyword', event.target.value)}
              />
            </Field>
            <Field label="保障类型">
              <select
                value={list.filters.category}
                onChange={(event) => list.updateFilter('category', event.target.value)}
              >
                <option value="">全部</option>
                {(dictionaries?.support_category || []).map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="保障等级">
              <select
                value={list.filters.level}
                onChange={(event) => list.updateFilter('level', event.target.value)}
              >
                <option value="">全部</option>
                {(dictionaries?.support_level || []).map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="保障状态">
              <select
                value={list.filters.status}
                onChange={(event) => list.updateFilter('status', event.target.value)}
              >
                <option value="">全部</option>
                {(dictionaries?.support_status || []).map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <button type="button" className="btn" onClick={list.resetFilters}>
              重置
            </button>
          </div>
        </section>

        <section className="card">
          <DataTable
            loading={list.loading}
            error={list.error}
            rows={list.items}
            emptyText="暂无保障方案"
            columns={[
              { key: 'code', title: '编号' },
              {
                key: 'name',
                title: '保障名称',
                wrap: true,
                render: (row) => <Link to={`/support/${row.id}`}>{row.name}</Link>,
              },
              { key: 'category', title: '类型' },
              { key: 'level', title: '等级', render: (row) => <SupportLevelTag level={row.level} /> },
              {
                key: 'period',
                title: '保障时段',
                render: (row) => `${formatDate(row.start_date)} ~ ${formatDate(row.end_date)}`,
              },
              {
                key: 'districts',
                title: '重点区域',
                wrap: true,
                render: (row) => (row.districts?.length ? row.districts.join('、') : '指定公厕'),
              },
              { key: 'inspections_per_day', title: '巡查频次', render: (row) => `${row.inspections_per_day} 次/日` },
              { key: 'duty_count', title: '值守班次' },
              { key: 'status', title: '状态', render: (row) => <StatusTag status={row.status} /> },
              {
                key: 'actions',
                title: '操作',
                render: (row) => (
                  <div className="inline">
                    <button
                      type="button"
                      className="btn-link"
                      onClick={() => navigate(`/support/${row.id}`)}
                    >
                      详情
                    </button>
                    {row.status === '筹备中' ? (
                      <button
                        type="button"
                        className="btn-link"
                        onClick={() =>
                          run(
                            () => supportApi.activate(row.id),
                            `确认启动「${row.name}」？将按${row.level}保障自动生成值守安排。`,
                            '保障已启动，值守安排已生成',
                          )
                        }
                      >
                        启动
                      </button>
                    ) : null}
                    {row.status === '进行中' ? (
                      <button
                        type="button"
                        className="btn-link"
                        onClick={() =>
                          run(
                            () => supportApi.finish(row.id),
                            `确认结束「${row.name}」？将自动生成保障情况小结。`,
                            '保障已结束，小结已生成',
                          )
                        }
                      >
                        结束
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn-link danger"
                      onClick={() =>
                        run(
                          () => supportApi.remove(row.id),
                          `确认删除保障方案「${row.name}」？其值守安排将一并删除。`,
                          '删除成功',
                        )
                      }
                    >
                      删除
                    </button>
                  </div>
                ),
              },
            ]}
          />
          <Pagination meta={list.meta} onPageChange={list.setPage} />
        </section>
      </div>

      {showForm ? (
        <SupportFormModal onClose={() => setShowForm(false)} onSaved={list.reload} />
      ) : null}
    </>
  );
}
