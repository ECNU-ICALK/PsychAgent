EMPATHY_MARKERS = ["听起来", "我在想", "我理解", "我注意到", "听上去", "你似乎", "我能感受到"]
OPEN_QUESTION_MARKERS = ["是什么让你", "能不能多讲讲", "可以说说", "当时你", "这对你意味着什么", "最让你困扰的部分是什么"]
AVOID_MARKERS = ["你应该", "你必须", "我建议你", "很简单", "别想了", "其实这没什么"]

def rule_based_reward(counselor_utt: str, client_utt: str) -> float:
    cu = counselor_utt.strip()
    cl = client_utt.strip()
    r = 0.0
    r += sum(1 for m in EMPATHY_MARKERS if m in cu) * 1.0
    r += sum(1 for m in OPEN_QUESTION_MARKERS if m in cu) * 1.0
    r -= sum(1 for m in AVOID_MARKERS if m in cu) * 1.5
    sents = sum(1 for x in cl.replace("！", "。").replace("?", "。").split("。") if x.strip())
    if sents >= 2:
        r += 0.5
    if len(cu) > 180:
        r -= 0.5
    return float(r)