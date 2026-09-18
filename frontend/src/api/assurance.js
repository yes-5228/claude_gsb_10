import { http } from './client.js';

const RESOURCE = '/assurances';

export const assuranceApi = {
  list: (params) => http.get(RESOURCE, params),
  detail: (id) => http.get(`${RESOURCE}/${id}`),
  create: (payload) => http.post(RESOURCE, payload),
  update: (id, payload) => http.patch(`${RESOURCE}/${id}`, payload),
  remove: (id, params) => http.delete(`${RESOURCE}/${id}`, params),
  start: (id, payload) => http.post(`${RESOURCE}/${id}/start`, payload),
  finish: (id, payload) => http.post(`${RESOURCE}/${id}/finish`, payload),
  cancel: (id, payload) => http.post(`${RESOURCE}/${id}/cancel`, payload),
  duties: (id, params) => http.get(`${RESOURCE}/${id}/duties`, params),
  updateDuty: (id, dutyId, payload) => http.patch(`${RESOURCE}/${id}/duties/${dutyId}`, payload),
  regenerate: (id) => http.post(`${RESOURCE}/${id}/duties/regenerate`),
  relink: (id) => http.post(`${RESOURCE}/${id}/relink-issues`),
  summary: (id) => http.get(`${RESOURCE}/${id}/summary`),
  refreshSummary: (id) => http.post(`${RESOURCE}/${id}/summary/refresh`),
};
