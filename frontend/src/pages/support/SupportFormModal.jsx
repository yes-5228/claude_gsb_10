import { useEffect, useState } from 'react';

import { metaApi } from '../../api/meta.js';
import { restroomApi } from '../../api/restrooms.js';
import { supportApi } from '../../api/support.js';
import Field from '../../components/Field.jsx';
import Modal from '../../components/Modal.jsx';
import { useToast } from '../../components/Toast.jsx';
import { useDictionaries } from '../../hooks/useDictionaries.js';

function toDateInput(value) {
  if (!value) return '';
  return String(value).slice(0, 10);
}

export default function SupportFormModal({ plan, onClose, onSaved }) {
  const { dictionaries } = useDictionaries();
  const toast = useToast();
  const isEdit = Boolean(plan);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [districtOptions, setDistrictOptions] = useState([]);
  const [restroomOptions, setRestroomOptions] = useState([]);
  const [form, setForm] = useState({
    name: plan?.name ?? '',
    category: plan?.category ?? '节假日',
    level: plan?.level ?? '二级',
    start_date: toDateInput(plan?.start_date),
    end_date: toDateInput(plan?.end_date),
    inspections_per_day: plan?.inspections_per_day ?? 2,
    requirements: plan?.requirements ?? '',
  });
  const [districts, setDistricts] = useState(plan?.districts ?? []);
  const [restroomIds, setRestroomIds] = useState(plan?.restroom_ids ?? []);
  const [staffText, setStaffText] = useState((plan?.staff_pool ?? []).join('\n'));

  useEffect(() => {
    restroomApi.districts().then(setDistrictOptions).catch((err) => setError(err.message));
    metaApi.restroomOptions().then(setRestroomOptions).catch((err) => setError(err.message));
  }, []);

  const patch = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const changeLevel = (level) => {
    const rule = dictionaries?.support_level_rules?.[level];
    setForm((prev) => ({
      ...prev,
      level,
      inspections_per_day: rule?.inspections_per_day ?? prev.inspections_per_day,
    }));
  };

  const toggle = (list, setList, value) => {
    setList(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  };

  const toggleRestroom = (id) => {
    setRestroomIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id],
    );
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) {
      setError('请填写保障名称');
      return;
    }
    if (!form.start_date || !form.end_date) {
      setError('请选择保障时段');
      return;
    }
    if (form.end_date < form.start_date) {
      setError('保障结束日期不能早于开始日期');
      return;
    }
    if (!districts.length && !restroomIds.length) {
      setError('请至少选择一个重点区域或重点公厕');
      return;
    }
    const staffPool = staffText
      .split('\n')
      .map((name) => name.trim())
      .filter(Boolean);
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...form,
        inspections_per_day: Number(form.inspections_per_day) || null,
        districts,
        restroom_ids: restroomIds,
        staff_pool: staffPool,
      };
      if (isEdit) {
        await supportApi.update(plan.id, payload);
      } else {
        await supportApi.create(payload);
      }
      toast.success(isEdit ? '保障方案已更新' : '保障方案已创建');
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const levelRule = dictionaries?.support_level_rules?.[form.level];

  return (
    <Modal
      title={isEdit ? '编辑保障方案' : '新增保障方案'}
      onClose={onClose}
      width={860}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            取消
          </button>
          <button type="submit" form="support-form" className="btn btn-primary" disabled={saving}>
            {saving ? '提交中…' : isEdit ? '保存修改' : '创建方案'}
          </button>
        </>
      }
    >
      {error ? <div className="alert alert-error">{error}</div> : null}
      <form id="support-form" onSubmit={submit} className="form-grid">
        <Field label="保障名称 *" full>
          <input
            value={form.name}
            placeholder="如：国庆黄金周公厕保障"
            onChange={(event) => patch('name', event.target.value)}
          />
        </Field>
        <Field label="保障类型">
          <select value={form.category} onChange={(event) => patch('category', event.target.value)}>
            {(dictionaries?.support_category || ['节假日', '重大活动']).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        <Field label="保障等级">
          <select value={form.level} onChange={(event) => changeLevel(event.target.value)}>
            {(dictionaries?.support_level || ['一级', '二级', '三级']).map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        <Field label="开始日期 *">
          <input
            type="date"
            value={form.start_date}
            onChange={(event) => patch('start_date', event.target.value)}
          />
        </Field>
        <Field label="结束日期 *">
          <input
            type="date"
            value={form.end_date}
            onChange={(event) => patch('end_date', event.target.value)}
          />
        </Field>
        <Field
          label="每公厕每日巡查频次"
          hint={levelRule ? `${form.level}保障默认 ${levelRule.inspections_per_day} 次/日，值守班次：${levelRule.shifts.join('、')}` : ''}
        >
          <input
            type="number"
            min="1"
            max="10"
            value={form.inspections_per_day}
            onChange={(event) => patch('inspections_per_day', event.target.value)}
          />
        </Field>
        <Field label="值守人员（每行一人）">
          <textarea
            rows="3"
            value={staffText}
            placeholder={'张伟\n刘洋\n胡明月'}
            onChange={(event) => setStaffText(event.target.value)}
          />
        </Field>
        <Field label="重点区域（按区域）" full>
          <div className="form-grid">
            {districtOptions.map((district) => (
              <label className="checkbox-row" key={district}>
                <input
                  type="checkbox"
                  checked={districts.includes(district)}
                  onChange={() => toggle(districts, setDistricts, district)}
                />
                {district}
              </label>
            ))}
            {!districtOptions.length ? <span className="hint">暂无区域数据</span> : null}
          </div>
        </Field>
        <Field label="重点公厕（可额外指定）" full>
          <div className="form-grid" style={{ maxHeight: 180, overflowY: 'auto' }}>
            {restroomOptions.map((option) => (
              <label className="checkbox-row" key={option.id}>
                <input
                  type="checkbox"
                  checked={restroomIds.includes(option.id)}
                  onChange={() => toggleRestroom(option.id)}
                />
                {option.code} {option.name}（{option.district}）
              </label>
            ))}
          </div>
        </Field>
        <Field label="保障要求" full>
          <textarea
            rows="3"
            value={form.requirements}
            placeholder="保障期间的巡查、保洁、值守与问题处置要求"
            onChange={(event) => patch('requirements', event.target.value)}
          />
        </Field>
      </form>
    </Modal>
  );
}
