import { http } from './client.js';

const RESOURCE = '/support-plans';

export const supportApi = {
  list: (params) => http.get(RESOURCE, params),
  detail: (id) => http.get(`${RESOURCE}/${id}`),
  create: (payload) => http.post(RESOURCE, payload),
  update: (id, payload) => http.patch(`${RESOURCE}/${id}`, payload),
  remove: (id) => http.delete(`${RESOURCE}/${id}`),
  activate: (id) => http.post(`${RESOURCE}/${id}/activate`),
  finish: (id) => http.post(`${RESOURCE}/${id}/finish`),
  generateDuties: (id) => http.post(`${RESOURCE}/${id}/duties/generate`),
  issues: (id, params) => http.get(`${RESOURCE}/${id}/issues`, params),
  summary: (id) => http.get(`${RESOURCE}/${id}/summary`),
};
