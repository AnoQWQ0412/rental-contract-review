// ============================================================
// agent.js —— 纯客户端 agentic loop
// 浏览器/手机直接调 API（支持多家厂商），key 在 localStorage
// 对应 Python 版 agent.py 的 Agent.run()
// ============================================================

const SYSTEM_PROMPT = `你是一名资深的租赁合同审查员，能处理各类租赁合同（住宅、商铺、办公、设备、车辆等）。

审查流程：
1. 阅读输入的全文，先判断它属于什么类型（住宅/商铺/办公/设备/车辆/其他/非租赁）
2. 必须调用 load_skill 加载『通用』规程（基础风险检查清单）
3. 再调用 load_skill 加载对应类型的专属规程；无法确定类型则加载『其他』
4. 按两份规程逐条核对合同，输出审查结果
5. 需要法规依据时调用 lookup_regulation 查证

工具使用规则：
- load_skill 和 lookup_regulation 是用来获取外部知识的，应当使用
- 不要调用工具去"读合同"——合同全文已在上方，直接阅读即可
- 已加载的规程不要重复加载

审查要求：
1. 只根据合同原文判断，不臆测条款内容
2. 未约定的点如实记录为"未约定"，而不是"无风险"
3. 条款不明确或证据不足 → 标"待复核"，不强行下结论
4. 输出 JSON 格式，结构为：
   {"document_type": "住宅/商铺/办公/设备/车辆/其他/非租赁",
    "risks": [{"item": "风险点名称", "level": "高/中/低/待复核", "detail": "风险描述", "basis": "依据的条款或规程"}],
    "pass": "是/否/待复核", "summary": "总体评价"}

非租赁内容处理：如果输入不是租赁合同，document_type 填"非租赁"，risks 可为空，summary 中说明这更可能是什么合同。`;

// 单次调用 API（浏览器 fetch）——地址/模型/key 都从配置动态读取
async function callAPI(apiKey, messages, tools) {
  const baseUrl = getBaseUrl();
  const model = getModel();
  if (!baseUrl) throw new Error("未配置 API 地址（自定义厂商需填写 base_url）");
  if (!model) throw new Error("未选择模型");

  const resp = await fetch(baseUrl + "/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: model,
      max_tokens: 8192,
      messages: messages,
      tools: tools,
      response_format: { type: "json_object" },
    }),
  });

  if (!resp.ok) {
    let detail = "";
    try { detail = (await resp.json()).error?.message || ""; } catch (e) {}
    throw new Error(`API 错误 ${resp.status}: ${detail || resp.statusText}`);
  }
  const data = await resp.json();
  return data.choices[0].message;
}

// 校验模型输出是否为合法的审查报告 JSON（简单结构校验）
function validateResult(content) {
  const obj = JSON.parse(content);
  if (!obj || typeof obj !== "object") throw new Error("输出不是对象");
  const legalLevel = ["高", "中", "低", "待复核"];
  const legalType = ["住宅", "商铺", "办公", "设备", "车辆", "其他", "非租赁"];
  if (!legalType.includes(obj.document_type)) obj.document_type = "其他";
  if (!["是", "否", "待复核"].includes(obj.pass)) obj.pass = "待复核";
  if (!Array.isArray(obj.risks)) obj.risks = [];
  for (const r of obj.risks) {
    if (!legalLevel.includes(r.level)) r.level = "待复核";
  }
  obj.summary = obj.summary || "";
  return obj;
}

// 主入口：审查一份合同，返回审查报告对象
// onLog: (msg) => void  用于显示工具调用过程
async function runReview(apiKey, contractText, onLog) {
  window.__contract = contractText;   // 供 search_clause 工具读取

  const messages = [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: contractText },
  ];

  for (let turn = 0; turn < 20; turn++) {
    const msg = await callAPI(apiKey, messages, TOOLS);

    if (!msg.tool_calls || msg.tool_calls.length === 0) {
      // 模型回答完毕 → 校验输出
      try {
        return validateResult(msg.content);
      } catch (e) {
        // 自修复：让模型重新输出完整 JSON
        messages.push({ role: "assistant", content: msg.content });
        messages.push({
          role: "user",
          content: "你上面的输出不是合法的 JSON 或结构不完整。请重新输出，只输出符合要求结构的完整 JSON，不要任何解释。",
        });
        const retry = await callAPI(apiKey, messages, []);
        return validateResult(retry.content);
      }
    }

    // 模型想调用工具 → 原样记录 assistant 消息
    messages.push({ role: "assistant", content: msg.content, tool_calls: msg.tool_calls });

    // 逐个执行工具，结果以 role="tool" 追加
    for (const call of msg.tool_calls) {
      let args = {};
      try { args = JSON.parse(call.function.arguments || "{}"); } catch (e) {}
      if (onLog) onLog(`[工具调用] ${call.function.name} ${JSON.stringify(args)}`);
      const result = executeTool(call.function.name, args);
      messages.push({ role: "tool", tool_call_id: call.id, content: result });
    }
  }

  throw new Error("达到最大轮数（20），任务未完成");
}
