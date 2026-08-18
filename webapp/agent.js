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

// 检测是否运行在 Capacitor 原生环境（打包成 APK 的 Android WebView）
function isNativeCapacitor() {
  return typeof Capacitor !== "undefined"
    && typeof Capacitor.isNativePlatform === "function"
    && Capacitor.isNativePlatform();
}

// 获取原生 HTTP 通道（Capacitor 内置，随 @capacitor/core 提供）
function getNativeHttp() {
  if (typeof CapacitorHttp !== "undefined") return CapacitorHttp;
  if (Capacitor && Capacitor.Plugins && Capacitor.Plugins.CapacitorHttp) return Capacitor.Plugins.CapacitorHttp;
  return null;
}

// 单次调用 API——地址/模型/key 都从配置动态读取
// 原生环境走原生 HTTP（绕过 CORS，可直连 opencode.ai 等未开放 CORS 的服务）；
// 网页环境（浏览器预览）走普通 fetch，需要服务支持 CORS。
async function callAPI(apiKey, messages, tools) {
  const baseUrl = getBaseUrl();
  const model = getModel();
  if (!baseUrl) throw new Error("未配置 API 地址（自定义厂商需填写 base_url）");
  if (!model) throw new Error("未选择模型");

  const base = (baseUrl || "").trim().replace(/\/+$/, "");
  // 兼容两种填法：填到 /v1（自动补 /chat/completions）或直接填完整端点（不重复拼）
  const endpoint = base.endsWith("/chat/completions") ? base : base + "/chat/completions";

  const payload = {
    model: model,
    max_tokens: 8192,
    messages: messages,
    tools: tools,
    response_format: { type: "json_object" },
  };
  const headers = {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${apiKey}`,
  };

  // 原生环境 → 用原生 HTTP 请求，绕开浏览器 CORS 限制
  if (isNativeCapacitor()) {
    const nativeHttp = getNativeHttp();
    const resp = await nativeHttp.post({ url: endpoint, headers, data: payload });
    if (resp.status < 200 || resp.status >= 300) {
      let detail = "";
      try { detail = resp.data && resp.data.error && resp.data.error.message || ""; } catch (e) {}
      throw new Error(`API 错误 ${resp.status}: ${detail || ""}`);
    }
    return resp.data.choices[0].message;
  }

  // 网页环境 / 未开启 CapacitorHttp 时的兜底 → 普通 fetch
  // （若已在 capacitor.config.json 开启 CapacitorHttp.enabled，APK 内这里也会被自动桥接到原生）
  const resp = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
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

// ============================================================
// 风险点补充查询：法律依据 + 适用解释 + 应对建议
// 审查完成后，用户可针对具体风险点点击发起一次查询
// ============================================================
const LEGAL_ADVICE_PROMPT = `你是一名资深法律顾问，擅长租赁合同纠纷。针对用户给出的'风险点'，请输出：
1. 相关法律法规条文原文（引用具体法律名称和条款号，如《中华人民共和国民法典》第七百零八条）
2. 该条文对风险点的适用解释（为什么这条法律涉及/能解决这个风险）
3. 给当事人（承租方或出租方）的应对补充建议（具体、可操作）

只输出 JSON，不要任何多余内容：
{"law": "法条原文（含法律名称和条款号）", "interpretation": "适用解释", "suggestion": "应对建议"}

若没有完全直接对应的法条：law 写"暂无直接对应法条（依据一般法律原则）"，interpretation 说明所依据的法律原则，suggestion 给出实操建议。`;

// 查询某个风险点的法律依据与建议
// contractText 只带前 1500 字摘要，节省 token
async function queryLegalAdvice(apiKey, risk, contractText) {
  const messages = [
    { role: "system", content: LEGAL_ADVICE_PROMPT },
    { role: "user", content: JSON.stringify({
      risk: { item: risk.item, detail: risk.detail, basis: risk.basis },
      contract: (contractText || "").slice(0, 1500),
    })},
  ];
  const msg = await callAPI(apiKey, messages, []);
  return validateLegalAdvice(msg.content);
}

function validateLegalAdvice(content) {
  try {
    const obj = JSON.parse(content);
    return {
      law: obj.law || "暂无法条",
      interpretation: obj.interpretation || "",
      suggestion: obj.suggestion || "",
    };
  } catch (e) {
    // 输出不是合法 JSON 时，把原文作为解释兜底展示
    return { law: "", interpretation: String(content), suggestion: "" };
  }
}

// ============================================================
// 连接检测：用极小请求分层排查 配置/网络/端点/认证/模型/CORS
// 几乎不消耗 token（max_tokens=1）
// 返回 { finalOk, steps:[{ok,msg}], summary }
// ============================================================
async function testConnection(apiKey) {
  const steps = [];
  const add = (ok, msg) => steps.push({ ok, msg });

  // ① 配置完整性检查（不发请求）
  const baseUrl = (getBaseUrl() || "").trim();
  const model = (getModel() || "").trim();
  const providerId = getProviderId();

  if (!baseUrl) {
    add(false, "未配置 API 地址：请到「设置」选择厂商，或自定义填 base_url");
    return { finalOk: false, steps, summary: "缺少 API 地址" };
  }
  if (!model && providerId === "custom") {
    add(false, "未填写模型名（自定义厂商）：请在设置里输入模型名，如 deepseek-chat");
    return { finalOk: false, steps, summary: "缺少模型名" };
  }
  if (!apiKey) {
    add(false, "未配置 API Key：请到「设置」填入你的 key");
    return { finalOk: false, steps, summary: "缺少 API Key" };
  }

  const base = baseUrl.replace(/\/+$/, "");
  const endpoint = base.endsWith("/chat/completions") ? base : base + "/chat/completions";
  add(true, `配置完整：模型=${model || "(将用预设默认)"} · 端点=${endpoint}`);

  const isNative = isNativeCapacitor();

  // ② 网页环境：先探测网络可达性
  //    no-cors 不受 CORS 限制——能成功说明网络通但服务可能未开放 CORS；
  //    失败则说明网络/地址/服务本身不可达。
  if (!isNative) {
    try {
      await fetch(endpoint, {
        method: "POST", mode: "no-cors",
        headers: { "Content-Type": "text/plain" }, body: "{}",
      });
      add(true, "网络连通，服务可达");
    } catch (e) {
      add(false, "网络连接失败或服务不可达：请检查是否联网、地址是否拼写正确、服务是否在线");
      return { finalOk: false, steps, summary: "网络层出错，请检查网络/地址" };
    }
  }

  // ③ 真实最小请求：验证 key / 模型 / 服务状态
  const payload = { model, messages: [{ role: "user", content: "ok" }], max_tokens: 1 };
  const headers = { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` };

  try {
    let status, data = {};
    if (isNative) {
      const r = await getNativeHttp().post({ url: endpoint, headers, data: payload });
      status = r.status; data = r.data || {};
    } else {
      const r = await fetch(endpoint, { method: "POST", headers, body: JSON.stringify(payload) });
      status = r.status;
      data = await r.json().catch(() => ({}));
    }

    if (status >= 200 && status < 300) {
      add(true, `API 请求成功（HTTP ${status}），服务可用！`);
      return { finalOk: true, steps, summary: "✅ 连接正常，可以开始审查了" };
    }
    if (status === 401 || status === 403) {
      add(false, `认证失败（HTTP ${status}）：API Key 无效或无权限，请检查 key 是否复制完整、是否已过期`);
      return { finalOk: false, steps, summary: "API Key 有问题" };
    }
    if (status === 404) {
      add(false, "地址/路径有误（HTTP 404）：检查 base_url 是否多拼了路径或填错了地址");
      return { finalOk: false, steps, summary: "API 地址有误" };
    }
    if (status === 400 || status === 422) {
      const msg = (data && data.error && data.error.message) || "";
      add(false, `请求被拒绝（HTTP ${status}）：很可能是模型名不对或该服务不支持此请求。${msg ? "服务端提示：" + msg : ""}`);
      return { finalOk: false, steps, summary: "模型名或请求格式可能有问题" };
    }
    add(false, `服务端错误（HTTP ${status}）：可能是余额不足、额度用尽或服务不稳定，请稍后重试`);
    return { finalOk: false, steps, summary: "服务端出错，可能涉及余额/额度/稳定性" };
  } catch (e) {
    if (!isNative) {
      // 网络探测通过（no-cors 成功）但真实请求失败 → 几乎可断定是 CORS 拦截
      add(false, "该服务未开放跨域权限（CORS）：网页版受浏览器限制无法直连。请使用打包的 App（原生请求不受限），或更换支持 CORS 的服务（如 DeepSeek / 通义 / 智谱官方）");
      return { finalOk: false, steps, summary: "CORS 限制，网页版无法直连此服务" };
    }
    add(false, "请求失败：" + String(e.message || e).slice(0, 120));
    return { finalOk: false, steps, summary: "请求失败，请检查网络或服务状态" };
  }
}
