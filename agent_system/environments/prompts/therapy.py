CLIENT_SYSTEM_TEMPLATE = (
    "你是来访者，处于心理咨询的第一节会谈。"
    "背景：姓名：{name}；年龄：{age}；性别：{gender}；职业：{job}。"
    "主要困扰：{problem}。性格特征：{personality}。来访目标：{goals}。"
    # "要求：只以第一人称、自然口语表达你的想法和感受；避免一次说太多；每次回复 1~4 句。"
)
CLIENT_INIT_USER = "请以第一人称给出开场陈述（1~3句），自然表达当前处境和感受。"

COUNSELOR_OBS_TEMPLATE = (
    "【任务】你是咨询师。下面是与来访者最近的对话历史（最多{hist_n}轮）：\n"
    "{history}\n"
    "【当前来访者】\n{current_client}\n"
    "【要求】用专业、简洁、共情的中文回应（1~4句），避免给建议式评判、避免一次问多个问题。"
)

# For Manager text building
# COUNSELING_TEMPLATE_NO_HIS = (
#     "【角色】你是心理咨询师。\n"
#     "【来访者画像】姓名：{name}；年龄：{age}；性别：{gender}；职业：{job}\n"
#     "【主要困扰】{problem}\n"
#     "【目标】{goals}\n\n"
#     "【当前来访者（开场）】\n{current_client}\n\n"
#     "【要求】本轮由你先开场，请用简短、共情的问候开始，并提出一个简洁的问题引导来访者分享"
# )

COUNSELING_TEMPLATE_NO_HIS = (
    "【角色】你是心理咨询师。\n"
    "【来访者画像】姓名：{name}；年龄：{age}；性别：{gender}；职业：{job}\n"
    "【主要困扰】{problem}\n"
    "【目标】{goals}\n\n"
    "【要求】本轮由你先开场，请用简短、共情的问候开始，并提出一个简洁的问题引导来访者分享"
)

COUNSELING_TEMPLATE = (
    "【角色】你是心理咨询师。\n"
    "【来访者画像】姓名：{name}；年龄：{age}；性别：{gender}；职业：{job}\n"
    "【主要困扰】{problem}\n"
    "【目标】{goals}\n"
    "【对话历史（最近{history_length}轮）】\n"
    "{action_history}\n"
    "【统计】已完成轮数：{step_count}；即将进行：第{current_step}轮\n\n"
    "【当前来访者】\n{current_client}\n\n"
    "【要求】以共情、开放式提问为主，1~4句中文回复，避免评判/建议口吻。"
)
