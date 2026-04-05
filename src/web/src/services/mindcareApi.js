import { requestJson } from "./http";

export const catalogApi = {
  async listSchools() {
    return requestJson("/schools");
  },
  async listStages() {
    return requestJson("/stages");
  },
};

export const authApi = {
  async login(payload) {
    return requestJson("/auth/login", { method: "POST", body: payload });
  },
  async register(payload) {
    return requestJson("/auth/register", { method: "POST", body: payload });
  },
};

function buildQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  });
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

// New hierarchical API
export const coursesApi = {
  async list(params = {}, { token, onUnauthorized } = {}) {
    return requestJson(`/courses${buildQuery(params)}`, { token, onUnauthorized });
  },
  async create(payload, { token, onUnauthorized } = {}) {
    return requestJson("/courses", {
      method: "POST",
      body: payload,
      token,
      onUnauthorized,
    });
  },
  async getById(courseId, { token, onUnauthorized } = {}) {
    return requestJson(`/courses/${courseId}`, { token, onUnauthorized });
  },
  async update(courseId, payload, { token, onUnauthorized } = {}) {
    return requestJson(`/courses/${courseId}`, {
      method: "PATCH",
      body: payload,
      token,
      onUnauthorized,
    });
  },
  async complete(courseId, payload = {}, { token, onUnauthorized } = {}) {
    return requestJson(`/courses/${courseId}/complete`, {
      method: "POST",
      body: payload,
      token,
      onUnauthorized,
    });
  },
  async archive(courseId, { token, onUnauthorized } = {}) {
    return requestJson(`/courses/${courseId}/archive`, {
      method: "POST",
      token,
      onUnauthorized,
    });
  },
};

export const visitsApi = {
  async list(courseId, { token, onUnauthorized } = {}) {
    return requestJson(`/courses/${courseId}/visits`, { token, onUnauthorized });
  },
  async create(courseId, payload = {}, { token, onUnauthorized } = {}) {
    return requestJson(`/courses/${courseId}/visits`, {
      method: "POST",
      body: payload,
      token,
      onUnauthorized,
    });
  },
  async getById(visitId, { token, onUnauthorized } = {}) {
    return requestJson(`/visits/${visitId}`, { token, onUnauthorized });
  },
  async sendMessage(visitId, payload, { token, onUnauthorized } = {}) {
    return requestJson(`/visits/${visitId}/messages`, {
      method: "POST",
      body: payload,
      token,
      onUnauthorized,
    });
  },
  async close(visitId, payload = {}, { token, onUnauthorized } = {}) {
    return requestJson(`/visits/${visitId}/close`, {
      method: "POST",
      body: payload,
      token,
      onUnauthorized,
    });
  },
};
