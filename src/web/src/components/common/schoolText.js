const SCHOOL_DISPLAY_NAME_MAP = {
  behavioral: "行为疗法 (BT)",
  cbt: "认知行为疗法 (CBT)",
  humanistic: "人本-存在主义疗法 (HET)",
  psychodynamic: "心理动力学疗法 (PDT)",
  postmodern: "后现代主义疗法 (PMT)",
};

export function getSchoolDisplayName(school) {
  if (!school) return "未选择";
  const mapped = SCHOOL_DISPLAY_NAME_MAP[school.id];
  if (mapped) return mapped;
  return school.name || "未选择";
}
