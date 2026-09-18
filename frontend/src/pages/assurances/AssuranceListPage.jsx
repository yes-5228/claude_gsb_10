import { useState } from 'react';
import { Link } from 'react-router-dom';

import { assuranceApi } from '../../api/assurance.js';
import { AssuranceLevelTag, AssuranceStatusTag } from '../../components/Tags.jsx';
import DataTable from '../../components/DataTable.jsx';
import Field from '../../components/Field.jsx';
import PageHeader from '../../components/PageHeader.jsx';
import Pagination from '../../components/Pagination.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useDictionaries } from '../../hooks/useDictionaries.js';
import { useListQuery } from '../../hooks/useListQuery.js';
import { formatDate } from '../../utils/format.js';
import AssuranceFormModal from './AssuranceFormModal.jsx';

const DEFAULT_FILTERS = {
  keyword: '',
  status: '',
  level: '',
  assurance_type: '',
};

export default function AssuranceListPage() {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);

  const list = useListQuery((params) => assuranceApi.list(params), DEFAULT_FILTERS, 10);

  const remove = async (row) => {
    if (!window.confirm(`确认删除保障「${row.name}」？已归集问题将解除归属。`)) return;
    try {
      await assuranceApi.remove(row.id, { force: 'true' });
      toast.success('删除成功');
      list.reload();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const openCreate = () => {
    setEditTarget(null);
    setShowForm(true);
  };

  return (
    <>
      <PageHeader
        title="节假日 / 重大活动保障"
        description="维护保障时段、重点区域与保障要求，自动加密巡查频次并生成值守安排"
        actions={
          <button type="button" className="btn btn-primary" onClick={openCreate}>
            + 新建保障
          </button>
        }
      />
      <div className="content">
        <section className="card">
          <div className="filter-bar">
            <Field label="关键字" full>
              <input
                value={list.filters.keyword}
                placeholder="保障名称 / 编号 / 联络人"
                onChange={(event) => list.updateFilter('keyword', event.target.value)}
              />
            </Field>
            <Field label="保障状态">
              <select
                value={list.filters.status}
                onChange={(event) => list.updateFilter('status', event.target.value)}
              >
                <option value="">全部</option>
                {(dictionaries?.assurance_status || []).map((item) => (
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
                {(dictionaries?.assurance_level || []).map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="保障类型">
              <select
                value={list.filters.assurance_type}
                onChange={(event) => list.updateFilter('assurance_type', event.target.value)}
              >
                <option value="">全部</option>
                {(dictionaries?.assurance_type || []).map((item) => (
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
            emptyText="暂无保障任务"
            columns={[
              { key: 'code', title: '编号', width: 150 },
              {
                key: 'name',
                title: '保障名称',
                wrap: true,
                render: (row) => <Link to={`/assurances/${row.id}`}>{row.name}</Link>,
              },
              { key: 'assurance_type', title: '类型' },
              {
                key: 'level',
                title: '等级',
                render: (row) => <AssuranceLevelTag level={row.level} />,
              },
              {
                key: 'status',
                title: '状态',
                render: (row) => <AssuranceStatusTag status={row.status} />,
              },
              {
                key: 'period',
                title: '保障时段',
                render: (row) => `${formatDate(row.start_date)} ~ ${formatDate(row.end_date)}`,
              },
              {
                key: 'target_count',
                title: '重点公厕',
                render: (row) => `${row.target_count} 座`,
              },
              { key: 'contact', title: '联络人' },
              {
                key: 'actions',
                title: '操作',
                render: (row) => (
                  <div className="inline">
                    <Link className="btn-link" to={`/assurances/${row.id}`}>
                      详情 / 值守
                    </Link>
                    {row.status === '筹备中' ? (
                      <button
                        type="button"
                        className="btn-link"
                        onClick={() => {
                          setEditTarget(row);
                          setShowForm(true);
                        }}
                      >
                        编辑
                      </button>
                    ) : null}
                    <button type="button" className="btn-link danger" onClick={() => remove(row)}>
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
        <AssuranceFormModal
          assurance={editTarget}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            list.reload();
          }}
        />
      ) : null}
    </>
  );
}
