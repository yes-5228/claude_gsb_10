import { useEffect, useMemo, useState } from 'react';

import { assuranceApi } from '../../api/assurance.js';
import { metaApi } from '../../api/meta.js';
import { restroomApi } from '../../api/restrooms.js';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useAsync } from '../../hooks/useAsync.js';
import { useDictionaries } from '../../hooks/useDictionaries.js';

function toDateInput(value) {
  const date = value ? new Date(value) : new Date();
  const pad = (num) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// 与后端 resolve_shift_plan 一致：以等级预置为底，手动 daily 的增量加早班、减量从晚班起扣，每班保底 1
function effectiveShiftPlan(frequency, daily) {
  if (!frequency) return null;
  const plan = { ...frequency.by_shift };
  if (daily == null) return { daily: frequency.daily, plan };
  const order = ['晚班', '中班', '早班'];
  let delta = daily - frequency.daily;
  if (delta > 0) plan['早班'] += delta;
  else if (delta < 0) {
    let remaining = -delta;
    for (const shift of order) {
      const take = Math.min(remaining, plan[shift] - 1);
      plan[shift] -= take;
      remaining -= take;
      if (remaining === 0) break;
    }
  }
  return { daily, plan };
}

export default function AssuranceFormModal({ assurance, onClose, onSaved }) {
  const isEdit = Boolean(assurance);
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const [districts, setDistricts] = useState([]);
  const [restrooms, setRestrooms] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const defaultEnd = useMemo(() => {
    const date = new Date();
    date.setDate(date.getDate() + 6);
    return date;
  }, []);

  const [form, setForm] = useState({
    name: '',
    assurance_type: '节假日保障',
    level: '二级保障',
    start_date: toDateInput(new Date()),
    end_date: toDateInput(defaultEnd),
    districtSet: new Set(),
    restroomSet: new Set(),
    daily_count: '',
    requirements: [''],
    contact: '',
    remark: '',
  });

  // 区域下拉与全部公厕选项
  useAsync(() => restroomApi.districts().then(setDistricts), []);
  useAsync(() => metaApi.restroomOptions().then(setRestrooms), []);

  // 编辑态拉详情，回显重点区域与手动追加公厕
  const { data: editDetail } = useAsync(
    () => (isEdit ? assuranceApi.detail(assurance.id) : Promise.resolve(null)),
    [assurance?.id],
  );

  useEffect(() => {
    if (!editDetail) return;
    const districtSet = new Set(
      editDetail.targets.filter((t) => t.source === '区域纳入').map((t) => t.district),
    );
    const restroomSet = new Set(
      editDetail.targets.filter((t) => t.source === '手动指定').map((t) => t.restroom_id),
    );
    setForm((prev) => ({
      ...prev,
      name: editDetail.name,
      assurance_type: editDetail.assurance_type,
      level: editDetail.level,
      start_date: toDateInput(editDetail.start_date),
      end_date: toDateInput(editDetail.end_date),
      districtSet,
      restroomSet,
      daily_count: String(editDetail.daily_count ?? ''),
      requirements: editDetail.requirements.length ? editDetail.requirements : [''],
      contact: editDetail.contact || '',
      remark: editDetail.remark || '',
    }));
  }, [editDetail]);

  const frequency = dictionaries?.assurance_level_frequency?.[form.level];
  const effective = effectiveShiftPlan(frequency, form.daily_count === '' ? null : Number(form.daily_count));

  const restroomsByDistrict = useMemo(() => {
    const groups = {};
    restrooms.forEach((room) => {
      (groups[room.district] ||= []).push(room);
    });
    return groups;
  }, [restrooms]);

  const setValue = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const toggleDistrict = (district) => {
    setForm((prev) => {
      const next = new Set(prev.districtSet);
      if (next.has(district)) next.delete(district);
      else next.add(district);
      return { ...prev, districtSet: next };
    });
  };

  const toggleRestroom = (id) => {
    setForm((prev) => {
      const next = new Set(prev.restroomSet);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { ...prev, restroomSet: next };
    });
  };

  const setRequirement = (index, value) => {
    setForm((prev) => {
      const requirements = [...prev.requirements];
      requirements[index] = value;
      return { ...prev, requirements };
    });
  };

  const addRequirement = () =>
    setForm((prev) => ({ ...prev, requirements: [...prev.requirements, ''] }));
  const removeRequirement = (index) =>
    setForm((prev) => ({ ...prev, requirements: prev.requirements.filter((_, i) => i !== index) }));

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) return setError('请填写保障名称');
    if (!form.start_date || !form.end_date) return setError('请选择保障起止日期');
    if (form.end_date < form.start_date) return setError('结束日期不能早于开始日期');
    if (!form.districtSet.size && !form.restroomSet.size)
      return setError('请至少选择一个重点区域或重点公厕');

    const payload = {
      name: form.name.trim(),
      assurance_type: form.assurance_type,
      level: form.level,
      start_date: form.start_date,
      end_date: form.end_date,
      districts: Array.from(form.districtSet),
      restroom_ids: Array.from(form.restroomSet),
      daily_count: form.daily_count === '' ? null : Number(form.daily_count),
      requirements: form.requirements.map((item) => item.trim()).filter(Boolean),
      contact: form.contact.trim(),
      remark: form.remark || null,
    };
    setSaving(true);
    setError(null);
    try {
      if (isEdit) await assuranceApi.update(assurance.id, payload);
      else await assuranceApi.create(payload);
      toast.success(isEdit ? '保障已更新并重新排班' : '保障已创建，值守安排已自动生成');
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={isEdit ? '编辑保障' : '新建保障'}
      onClose={onClose}
      width={860}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button type="submit" form="assurance-form" className="btn btn-primary" disabled={saving}>
            {saving ? '提交中...' : isEdit ? '保存并重排' : '创建并排班'}
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="assurance-form" className="form-grid" onSubmit={submit}>
        <Field label="保障名称 *" full>
          <input value={form.name} onChange={setValue('name')} placeholder="如：国庆假期重点区域保障" />
        </Field>
        <Field label="保障类型">
          <select value={form.assurance_type} onChange={setValue('assurance_type')}>
            {(dictionaries?.assurance_type || []).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        <Field label="保障等级">
          <select value={form.level} onChange={setValue('level')}>
            {(dictionaries?.assurance_level || []).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        <Field label="开始日期 *">
          <input type="date" value={form.start_date} onChange={setValue('start_date')} />
        </Field>
        <Field label="结束日期 *">
          <input type="date" value={form.end_date} onChange={setValue('end_date')} />
        </Field>
        <Field label="每日每厕巡查次数" hint="留空按等级预置，可在 3-12 间微调">
          <input
            type="number"
            min={3}
            max={12}
            value={form.daily_count}
            placeholder={`预置 ${frequency?.daily ?? ''} 次`}
            onChange={setValue('daily_count')}
          />
        </Field>
        <Field label="值班联络人">
          <input value={form.contact} onChange={setValue('contact')} placeholder="值班室 / 负责人" />
        </Field>
        <Field label="加密频次预览" full hint="按保障等级自动加密，按早/中/晚班次均摊">
          <div className="alert alert-info" style={{ margin: 0 }}>
            {effective
              ? `每日每厕 ${effective.daily} 次　|　早班 ${effective.plan['早班']} / 中班 ${effective.plan['中班']} / 晚班 ${effective.plan['晚班']} 次，系统据此自动生成天×班次×公厕值守岗位`
              : '加载频次中...'}
          </div>
        </Field>

        <Field label="重点区域（区内正常开放公厕全部纳入）" full>
          <div className="check-grid">
            {districts.map((district) => (
              <label className="check-item checkbox-row" key={district}>
                <input
                  type="checkbox"
                  checked={form.districtSet.has(district)}
                  onChange={() => toggleDistrict(district)}
                />
                <span className="name">{district}</span>
              </label>
            ))}
            {!districts.length ? <span className="muted">暂无区域</span> : null}
          </div>
        </Field>

        <Field label="追加重点公厕（区域外或个别重点对象）" full>
          <div className="check-grid">
            {Object.entries(restroomsByDistrict).map(([district, rooms]) => (
              <div key={district} style={{ gridColumn: '1 / -1' }}>
                <div className="muted" style={{ margin: '4px 0' }}>{district}</div>
                <div className="check-grid">
                  {rooms.map((room) => {
                    const viaDistrict = form.districtSet.has(room.district);
                    return (
                      <label className="check-item checkbox-row" key={room.id}>
                        <input
                          type="checkbox"
                          checked={viaDistrict || form.restroomSet.has(room.id)}
                          disabled={viaDistrict}
                          onChange={() => toggleRestroom(room.id)}
                        />
                        <span className="name">
                          {room.code} {room.name}
                          {viaDistrict ? <span className="muted">（区域已纳入）</span> : null}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </Field>

        <Field label="保障要求" full>
          <div className="bar-list">
            {form.requirements.map((requirement, index) => (
              <div className="inline" key={index}>
                <input
                  value={requirement}
                  placeholder={`保障要求 ${index + 1}，如：重点公厕每班次巡查不少于 2 次`}
                  onChange={(event) => setRequirement(index, event.target.value)}
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => removeRequirement(index)}
                  disabled={form.requirements.length === 1}
                >
                  删除
                </button>
              </div>
            ))}
            <div>
              <button type="button" className="btn btn-sm" onClick={addRequirement}>
                + 添加要求
              </button>
            </div>
          </div>
        </Field>

        <Field label="备注" full>
          <textarea rows="2" value={form.remark} onChange={setValue('remark')} />
        </Field>
      </form>
    </Modal>
  );
}
