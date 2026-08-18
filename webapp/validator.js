// ============================================================
// validator.js —— 输入校验（纯客户端规则层）
// 拦截无关输入，避免浪费 token。对应 Python 版 validator.py
// ============================================================

const RENTAL_KEYWORDS = ["出租", "承租", "押金", "租金", "租期", "出租方", "承租方", "甲方", "乙方"];
const UNRELATED_HINTS = ["你好", "hello", "hi", "你是谁", "今天天气", "随便", "测试", "test"];
const NON_RENTAL_STRONG = ["借条", "借款", "贷款", "买卖合同", "劳动合同", "劳务合同", "工资", "欠条"];

// 返回 {ok, kind, reason}
function validateInput(text) {
  const stripped = (text || "").trim();
  if (!stripped) return { ok: false, kind: "无关内容", reason: "输入为空" };

  if (stripped.length < 10) return { ok: false, kind: "无关内容", reason: "输入太短，请粘贴合同全文" };

  const lower = stripped.toLowerCase();
  for (const h of UNRELATED_HINTS) {
    if (lower.includes(h)) return { ok: false, kind: "无关内容", reason: "输入看起来不是一份租赁合同，请粘贴合同文本" };
  }

  for (const s of NON_RENTAL_STRONG) {
    if (stripped.includes(s)) {
      if (stripped.includes("租赁") || stripped.includes("出租") || stripped.includes("承租") || stripped.includes("押金")) {
        break; // 仍可能是租赁，交给模型判断
      }
      return { ok: false, kind: "其他合同", reason: "这是一份其他类型的合同（非租赁），本应用目前只审查租赁合同" };
    }
  }

  // 明显是租赁（甲方/乙方 + 押金/租金）
  if (RENTAL_KEYWORDS.includes("出租方") || stripped.includes("甲方")) {
    if (["押金", "租金", "租期", "租赁"].some(k => stripped.includes(k))) {
      return { ok: true, kind: "租赁合同", reason: "" };
    }
  }

  // 歧义：放行，让模型判断（纯客户端不便调二次模型，省 token）
  return { ok: true, kind: "租赁合同", reason: "" };
}
