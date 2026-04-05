const COURSE_STATUS_LABELS = {
  active: "进行中",
  completed: "已完成",
  archived: "已归档",
};

const VISIT_STATUS_LABELS = {
  open: "进行中",
  closed: "已结束",
};

export function getCourseStatusText(status) {
  return COURSE_STATUS_LABELS[status] || "未知状态";
}

export function getVisitStatusText(status) {
  return VISIT_STATUS_LABELS[status] || "未知状态";
}

export function formatVisitLabel(visitNo) {
  const normalizedNo = Number(visitNo) || 0;
  return `第 ${normalizedNo} 次会谈`;
}
